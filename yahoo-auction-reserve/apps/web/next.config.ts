import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@yar/db", "@yar/shared"],
  serverExternalPackages: ["@prisma/client"],
  // 親リポジトリの package-lock.json も見えてしまうため、明示しないと Next が
  // ワークスペースルートを親リポジトリ側に誤推定する(standalone 出力のトレース範囲がズレる)。
  // next は apps/web を cwd として起動されるので、その2つ上がこのモノレポのルート。
  outputFileTracingRoot: path.resolve(process.cwd(), "../.."),
};

export default nextConfig;
