import { resolve } from "node:path";

// ローカル実行(npm run dev:worker / p0:probe / user:password など)用の
// 環境変数ファイル読み込み。
//
// docker compose では env_file で渡るので不要だが、ホストで直接動かす
// スクリプトには何も読み込む仕組みが無く、README どおりテンプレートを
// コピーしても DATABASE_URL 未定義で落ちる。
//
// ⚠️ ここに置いてあるのは「PrismaClient を作る前に必ず通る場所」だから。
//    以前は apps/worker/src/env.ts にだけ在り、worker のスクリプトは動くのに
//    web 側のスクリプト(apps/web/scripts/set-password.ts)だけが
//    `Environment variable not found: DATABASE_URL` で落ちた。
//    読み込みの責任を呼び出し側に置くと、**スクリプトを1本足すたびに
//    同じ落とし方をする**。写しを作らないこと。
//
// 既に定義済みの環境変数は上書きしない(compose 側の値が勝つ)。
// これは process.loadEnvFile の仕様(--env-file と同じ)。

// cwd はどこから呼ばれたかで変わる。
//   ルートの npm script            → <app>            → ".env"
//   npm run ... -w @yar/worker 等  → <app>/apps/xxx   → "../../.env"
const CANDIDATES = ["../../.env", ".env"];

let done = false;

/** 見つかった最初の env ファイルを読む。2回目以降は何もしない */
export function loadLocalEnv(): void {
  if (done) return;
  done = true;
  for (const rel of CANDIDATES) {
    try {
      process.loadEnvFile(resolve(process.cwd(), rel));
      return;
    } catch {
      // 見つからない/読めないときは既存の環境変数をそのまま使う
    }
  }
}
