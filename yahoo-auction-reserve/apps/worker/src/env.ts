import { resolve } from "node:path";

// ローカル実行(npm run dev:worker / npm run p0:probe)用の .env 読み込み。
//
// docker compose では env_file: .env で渡るので不要だが、ローカルでは何も
// 読み込む仕組みが無く、README どおり `cp .env.example .env` しても
// DATABASE_URL 未定義で落ちていた。
//
// queues.ts が module スコープで REDIS_URL を読むため、**副作用として
// import 時に読み込む**。呼び出し側では必ず最初の import にすること。
// 既に定義済みの環境変数は上書きしない(compose 側の値が勝つ)。
const CANDIDATES = ["../../.env", ".env"];

for (const rel of CANDIDATES) {
  try {
    process.loadEnvFile(resolve(process.cwd(), rel));
    break;
  } catch {
    // 見つからない/読めないときは既存の環境変数をそのまま使う
  }
}
