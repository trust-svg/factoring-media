import { prisma } from "@/lib/prisma";
import Link from "next/link";
import type { Metadata } from "next";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "管理画面",
  robots: { index: false, follow: false },
};

export default async function AdminPage() {
  const [companyCount, reviewCount, pendingReviewCount, estimateCount] =
    await Promise.all([
      prisma.company.count(),
      prisma.review.count(),
      prisma.review.count({ where: { isApproved: false } }),
      prisma.estimateRequest.count(),
    ]);

  return (
    <div className="max-w-4xl mx-auto px-4 py-10">
      <h1 className="text-2xl font-bold text-navy mb-8">管理画面</h1>

      <div className="grid md:grid-cols-4 gap-4 mb-8">
        <div className="bg-white border border-gray-200 rounded-xl p-5 text-center">
          <p className="text-3xl font-black text-navy">{companyCount}</p>
          <p className="text-sm text-gray-500 mt-1">登録業者数</p>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-5 text-center">
          <p className="text-3xl font-black text-navy">{reviewCount}</p>
          <p className="text-sm text-gray-500 mt-1">総口コミ数</p>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-5 text-center">
          <p className="text-3xl font-black text-warning">{pendingReviewCount}</p>
          <p className="text-sm text-gray-500 mt-1">未承認口コミ</p>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-5 text-center">
          <p className="text-3xl font-black text-green">{estimateCount}</p>
          <p className="text-sm text-gray-500 mt-1">見積もり依頼</p>
        </div>
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        <Link
          href="/admin/reviews"
          className="bg-white border border-gray-200 rounded-xl p-6 hover:shadow-md transition-shadow"
        >
          <h2 className="font-bold text-navy mb-2">口コミ管理</h2>
          <p className="text-sm text-gray-500">
            口コミの承認・削除を管理します
          </p>
          {pendingReviewCount > 0 && (
            <span className="inline-block mt-2 bg-warning text-white text-xs px-2 py-1 rounded-full">
              {pendingReviewCount}件の未承認
            </span>
          )}
        </Link>
        <Link
          href="/admin/estimates"
          className="bg-white border border-gray-200 rounded-xl p-6 hover:shadow-md transition-shadow"
        >
          <h2 className="font-bold text-navy mb-2">見積もり依頼</h2>
          <p className="text-sm text-gray-500">
            受信した見積もり依頼を確認します
          </p>
        </Link>
        <Link
          href="/admin/companies"
          className="bg-white border border-gray-200 rounded-xl p-6 hover:shadow-md transition-shadow"
        >
          <h2 className="font-bold text-navy mb-2">業者管理</h2>
          <p className="text-sm text-gray-500">
            ランキング順位やアフィリエイトリンクを管理します
          </p>
        </Link>
      </div>
    </div>
  );
}
