/**
 * 既存ユーザーのパスワードを設定し直す。
 *
 *   npm run user:password -- <メールアドレス>
 *
 * なぜ要るか: 新規登録は「ユーザーが0人のときだけ」自動的に開く設計
 * (packages/shared/src/access.ts)。初回セットアップが済んだ時点で閉じるので、
 * パスワードを忘れると **画面からは何もできなくなる**。
 * ALLOW_REGISTRATION=true で開けて別アカウントを作るのは、ヤフオク連携も
 * 予約も引き継がれないので解決にならない。
 *
 * ⚠️ パスワードは端末上でだけ入力する(引数にも環境変数にも渡さない)。
 *    引数に書くとシェル履歴と `ps` の出力に残る。
 */
import bcrypt from "bcryptjs";
import { prisma } from "@yar/db";

// register/route.ts と同じコスト。ここだけ弱いと、リセットした瞬間に
// 保護が下がるのに画面上は何も変わらない。
const BCRYPT_COST = 12;
const MIN_LENGTH = 12;

const CTRL_C = "\u0003";
const BACKSPACE = "\u007f";

/** 入力をエコーせずに1行読む */
async function readSecret(prompt: string): Promise<string> {
  process.stdout.write(prompt);
  const stdin = process.stdin;
  const wasRaw = stdin.isRaw;
  stdin.setRawMode(true);
  stdin.resume();
  stdin.setEncoding("utf-8");

  return await new Promise<string>((resolve, reject) => {
    let buf = "";
    const cleanup = () => {
      stdin.off("data", onData);
      stdin.setRawMode(wasRaw);
      stdin.pause();
    };
    const onData = (chunk: string) => {
      for (const ch of chunk) {
        if (ch === "\n" || ch === "\r") {
          cleanup();
          process.stdout.write("\n");
          resolve(buf);
          return;
        }
        if (ch === CTRL_C) {
          cleanup();
          process.stdout.write("\n");
          reject(new Error("中断しました(何も変更していません)"));
          return;
        }
        if (ch === BACKSPACE || ch === "\b") {
          buf = buf.slice(0, -1);
          continue;
        }
        buf += ch;
      }
    };
    stdin.on("data", onData);
  });
}

async function main() {
  const email = process.argv[2];
  if (!email) {
    console.error("使い方: npm run user:password -- <メールアドレス>");
    process.exit(1);
  }
  // 非対話で走らせるとエコーを止められず、パスワードが画面とログに残る。
  if (!process.stdin.isTTY) {
    console.error("端末から実行してください(パイプ・非対話では受け付けません)");
    process.exit(1);
  }

  const user = await prisma.user.findUnique({
    where: { email },
    select: { id: true, email: true },
  });
  // 存在しないアドレスを指定したときに黙って新規作成しない。
  // ここで作ると「ログインはできるが何も紐づいていない別人」が増える。
  if (!user) {
    const all = await prisma.user.findMany({ select: { email: true } });
    console.error(`${email} は登録されていません。`);
    console.error(`登録済み: ${all.map((u) => u.email).join(", ") || "(0件)"}`);
    process.exit(1);
  }

  const pw = await readSecret(`${user.email} の新しいパスワード: `);
  if (pw.length < MIN_LENGTH) {
    console.error(`短すぎます(${MIN_LENGTH}文字以上)。何も変更していません。`);
    process.exit(1);
  }
  const again = await readSecret("もう一度: ");
  if (pw !== again) {
    console.error("一致しません。何も変更していません。");
    process.exit(1);
  }

  await prisma.user.update({
    where: { id: user.id },
    data: { passwordHash: await bcrypt.hash(pw, BCRYPT_COST) },
  });
  console.log(`${user.email} のパスワードを更新しました。`);
  await prisma.$disconnect();
}

main().catch(async (err) => {
  console.error(err instanceof Error ? err.message : String(err));
  await prisma.$disconnect().catch(() => {});
  process.exit(1);
});
