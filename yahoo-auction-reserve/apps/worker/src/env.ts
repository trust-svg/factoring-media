import { loadLocalEnv } from "@yar/db";

// ローカル実行用の環境変数読み込み。実体は packages/db/src/loadEnv.ts。
//
// queues.ts が module スコープで REDIS_URL を読むため、**副作用として
// import 時に読み込む**。呼び出し側では必ず最初の import にすること。
//
// ⚠️ 以前はこのファイルが読み込みの実装そのものを持っていた。その結果、
//    worker のスクリプトだけが動き、web 側のスクリプトは
//    `Environment variable not found: DATABASE_URL` で落ちた。
//    実装は @yar/db に移してある(PrismaClient を作る前に必ず通る場所)。
loadLocalEnv();
