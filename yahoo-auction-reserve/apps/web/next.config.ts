import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@yar/db", "@yar/shared"],
  serverExternalPackages: ["@prisma/client"],
};

export default nextConfig;
