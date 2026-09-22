import path from "node:path";
import type { NextConfig } from "next";

// Next が .env を探すのは apps/web 配下だが、このリポジトリの .env はモノレポの
// ルートに1つだけ置く運用(docker compose の env_file と同じファイル)。
// next.config は dev/build/start のいずれでもサーバ側で評価されるので、ここで
// ルートの .env を読み込んでおく。既存の環境変数は上書きしない(compose 側が勝つ)。
try {
  process.loadEnvFile(path.resolve(process.cwd(), "../../.env"));
} catch {
  // .env が無い場合は環境変数がそのまま使われる
}

const nextConfig: NextConfig = {
  transpilePackages: ["@yar/db", "@yar/shared"],
  serverExternalPackages: ["@prisma/client"],
  // 親リポジトリの package-lock.json も見えてしまうため、明示しないと Next が
  // ワークスペースルートを親リポジトリ側に誤推定する(standalone 出力のトレース範囲がズレる)。
  // next は apps/web を cwd として起動されるので、その2つ上がこのモノレポのルート。
  outputFileTracingRoot: path.resolve(process.cwd(), "../.."),
};

export default nextConfig;
