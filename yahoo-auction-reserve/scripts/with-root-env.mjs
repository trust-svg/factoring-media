// モノレポのルートに1つだけ置く .env を読んでからコマンドを実行するラッパ。
//
// Prisma CLI は cwd(= packages/db)から .env を探すため、ルートの .env が
// 届かず `npm run db:push` だけが "Environment variable not found: DATABASE_URL"
// で落ちていた(docker compose は env_file で渡るので compose では再現しない)。
// worker は src/env.ts、web は next.config.ts が同じことをしている。
//
// 既に定義済みの環境変数は上書きしない(compose の environment: が常に勝つ)。
//
//   node scripts/with-root-env.mjs <コマンド> [引数...]
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");

try {
  process.loadEnvFile(resolve(root, ".env"));
} catch {
  // .env が無い場合は既存の環境変数をそのまま使う(CI・compose 経由)
}

const [cmd, ...args] = process.argv.slice(2);
if (!cmd) {
  console.error("usage: node scripts/with-root-env.mjs <command> [args...]");
  process.exit(2);
}

const child = spawn(cmd, args, { stdio: "inherit", shell: process.platform === "win32" });
child.on("exit", (code, signal) => {
  // シグナルで死んだときに exit 0 を返すと、呼び出し元が成功と誤認する
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 1);
});
child.on("error", (err) => {
  console.error(`${cmd} を起動できませんでした:`, err.message);
  process.exit(1);
});
