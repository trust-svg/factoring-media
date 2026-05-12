import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    formats: ["image/avif", "image/webp"],
  },
  async redirects() {
    return [
      // 旧ペイトナーレビュー記事（paytner-review.md に統合）
      {
        source: "/articles/paytoday-review",
        destination: "/articles/paytner-review",
        permanent: true,
      },
      // /companies/paytner の旧リンク（実体は slug "paytoday"）
      {
        source: "/companies/paytner",
        destination: "/companies/paytoday",
        permanent: true,
      },
    ];
  },
};

export default nextConfig;
