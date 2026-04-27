import { prisma } from "@/lib/prisma";
import { CompanyCard } from "@/components/CompanyCard";
import type { Metadata } from "next";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "ファクタリング業者一覧",
  description:
    "ファクタリング業者を手数料・入金速度・口コミ評価で比較。全業者の詳細情報と口コミを掲載しています。",
};

export default async function CompaniesPage() {
  const companies = await prisma.company.findMany({
    orderBy: { rankingOrder: "asc" },
  });

  return (
    <div className="max-w-6xl mx-auto px-4 py-10">
      <h1 className="text-2xl md:text-3xl font-bold text-navy mb-2">
        ファクタリング業者一覧
      </h1>
      <p className="text-gray-500 mb-8">
        全{companies.length}社の業者を比較できます。各業者の詳細ページでは口コミも確認できます。
      </p>

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
        {companies.map((company) => (
          <CompanyCard key={company.slug} {...company} />
        ))}
      </div>
    </div>
  );
}
