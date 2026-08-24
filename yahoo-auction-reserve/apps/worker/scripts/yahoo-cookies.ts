/**
 * =============================================================
 * ヤフオク Cookie 取得ヘルパー
 * =============================================================
 * ログイン維持に使う Cookie (T / Y / SSL / SSLK) は httpOnly なので、
 * `document.cookie` やブックマークレットでは取得できない。素直にやると
 * Cookie 編集系のブラウザ拡張が必要になるが、あの手の拡張は「全サイトの
 * Cookie を読める」権限を常時持つので、そのために入れるのは割に合わない。
 *
 * このスクリプトは、まっさらな Chromium を1つ立ち上げて人間がそこで
 * ヤフオクにログインし、そのウィンドウの Cookie だけを取り出す。
 * 普段使いの Chrome のプロファイルには一切触らない。
 *
 * 実行するのは人間。CI や worker からは呼ばないこと。
 *
 * 使い方:
 *   npm run yahoo:cookies              # ログイン画面を開く
 *   npm run yahoo:cookies -- --print   # クリップボードでなく標準出力に出す
 *
 * 既定ではクリップボードへコピーするだけで、**値は画面にもファイルにも出さない**。
 * そのまま http://localhost:3000/settings/yahoo のテキストエリアに貼り付ける。
 */
// 最初に .env を読む(module スコープで環境変数を読むモジュールがあるため順序が重要)
import "../src/env";
import { spawnSync } from "node:child_process";
import { createInterface } from "node:readline/promises";
import { chromium } from "playwright";
import { YAHOO_AUTH_COOKIE_NAMES } from "@yar/shared";

// ログイン後にここへ遷移していれば、ひとまずログインは通っている
const LOGIN_URL = "https://login.yahoo.co.jp/config/login";
const CHECK_URL = "https://auctions.yahoo.co.jp/";

interface Args {
  print: boolean;
}

function parseArgs(argv: string[]): Args {
  return { print: argv.includes("--print") };
}

function fmtExpiry(expires: number | undefined): string {
  // Playwright は「セッションCookie」を -1 で返す
  if (expires === undefined || expires <= 0) return "セッション(ブラウザを閉じるまで)";
  return new Date(expires * 1000).toLocaleString("ja-JP");
}

// クリップボードへ渡す。値を引数に置くと ps で見えてしまうので必ず stdin 経由。
function copyToClipboard(text: string): boolean {
  const cmd =
    process.platform === "darwin"
      ? { bin: "pbcopy", args: [] as string[] }
      : process.platform === "win32"
        ? { bin: "clip", args: [] }
        : { bin: "xclip", args: ["-selection", "clipboard"] };

  const r = spawnSync(cmd.bin, cmd.args, { input: text });
  return r.status === 0 && !r.error;
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));

  console.log("Chromium を起動します(普段使いの Chrome とは別のまっさらなプロファイル)。");
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  await page.goto(LOGIN_URL);

  console.log("");
  console.log("開いたウィンドウで Yahoo! JAPAN にログインしてください。");
  console.log("(2段階認証・SMS 認証がある場合も、そのウィンドウで最後まで済ませる)");
  console.log("");
  console.log("ログインできたら、このターミナルに戻って Enter を押してください。");

  const rl = createInterface({ input: process.stdin, output: process.stdout });
  await rl.question("");
  rl.close();

  // ログイン直後はまだ発行されていない Cookie があるので、
  // 一度オークショントップを踏んでから取り出す
  try {
    await page.goto(CHECK_URL, { waitUntil: "domcontentloaded", timeout: 30_000 });
  } catch {
    console.log("(オークショントップの読み込みに失敗しましたが、Cookie の取り出しは続けます)");
  }

  const all = await context.cookies();
  const cookies = all.filter((c) => c.domain.replace(/^\./, "").endsWith("yahoo.co.jp"));

  await browser.close();

  if (cookies.length === 0) {
    console.error("");
    console.error("yahoo.co.jp の Cookie が1件も取れませんでした。ログインが完了していない可能性があります。");
    process.exitCode = 1;
    return;
  }

  // 値は出さない。名前と失効時刻だけ(設計 §8)
  console.log("");
  console.log(`取得した Cookie: ${cookies.length} 件`);
  console.log("");
  console.log("| 名前 | ドメイン | httpOnly | 失効 |");
  console.log("|---|---|---|---|");
  for (const c of [...cookies].sort((a, b) => a.name.localeCompare(b.name))) {
    console.log(`| ${c.name} | ${c.domain} | ${c.httpOnly ? "はい" : "いいえ"} | ${fmtExpiry(c.expires)} |`);
  }

  const names = new Set(cookies.map((c) => c.name));
  const missing = YAHOO_AUTH_COOKIE_NAMES.filter((n) => !names.has(n));
  console.log("");
  if (missing.length > 0) {
    // ここで止めない。この4件が本当に必要かは P0 検証で確定させる前提のため(設計 §13)
    console.log(`⚠️  ログインに必要とみられる Cookie が足りません: ${missing.join(", ")}`);
    console.log("   ログインが完了していないか、必要な Cookie 名の想定が違う可能性があります。");
  } else {
    console.log(`✅ 想定していた認証 Cookie (${YAHOO_AUTH_COOKIE_NAMES.join(", ")}) は揃っています。`);
  }

  // storageState 形式。/settings/yahoo の正規化がこの形をそのまま受け取れる
  const json = JSON.stringify({ cookies }, null, 2);

  console.log("");
  if (args.print) {
    console.log("--- ここから下をコピーしてください(Cookie の値が含まれます) ---");
    console.log(json);
    return;
  }

  if (copyToClipboard(json)) {
    console.log("クリップボードにコピーしました。値は画面にもファイルにも出していません。");
    console.log("");
    console.log("次の手順:");
    console.log("  1. http://localhost:3000/settings/yahoo を開く");
    console.log("  2. ラベルに分かる名前(例: メイン)を入れる");
    console.log("  3. Cookie の欄に貼り付け(Cmd+V)て「登録する」");
    console.log("");
    console.log("※ 貼り付けが終わったらクリップボードは何か別のものをコピーして流してください。");
  } else {
    console.error("クリップボードへのコピーに失敗しました。--print を付けて実行し、表示された JSON をコピーしてください。");
    process.exitCode = 1;
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
