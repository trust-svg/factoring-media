import { prisma } from "@/lib/prisma";
import { RankingTable } from "@/components/RankingTable";
import { ComparisonTable } from "@/components/ComparisonTable";
import type { Metadata } from "next";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "ファクタリング業者おすすめランキング【2026年3月最新版】",
  description:
    "ファクタリング業者のおすすめランキング。手数料・入金速度・口コミ評価を総合的に比較し、厳選した業者をランキング形式でご紹介します。",
};

export default async function RankingPage() {
  const companies = await prisma.company.findMany({
    orderBy: { rankingOrder: "asc" },
  });

  return (
    <div className="max-w-4xl mx-auto px-4 py-10">
      <h1 className="text-2xl md:text-3xl font-bold text-navy mb-2">
        ファクタリング業者おすすめランキング
      </h1>
      <p className="text-sm text-gray-500 mb-2">2026年3月最新版</p>
      <p className="text-gray-600 mb-8">
        手数料・入金速度・口コミ評価を独自の基準で総合的に評価し、ランキング形式でご紹介しています。
      </p>

      {/* Comparison Table */}
      <div className="mb-12">
        <h2 className="text-xl font-bold text-navy mb-4">主要業者比較表</h2>
        <ComparisonTable companies={companies} />
      </div>

      {/* Ranking Cards */}
      <div className="mb-12">
        <h2 className="text-xl font-bold text-navy mb-6">詳細ランキング</h2>
        <RankingTable companies={companies} />
      </div>

      {/* CTA */}
      <div className="bg-navy rounded-xl p-8 text-center text-white">
        <h2 className="text-xl font-bold mb-3">
          どの業者を選べばいいか迷ったら
        </h2>
        <p className="text-gray-300 mb-6">
          無料の無料診断で、あなたの条件に最適な業者をご紹介します
        </p>
        <a
          href="/estimate"
          className="inline-block bg-green hover:bg-green-dark text-white px-8 py-4 rounded-xl font-bold transition-colors shadow-lg"
        >
          無料で診断する
        </a>
      </div>
    </div>
  );
}
