import { prisma } from "@/lib/prisma";
import { Stars } from "@/components/CompanyCard";
import type { Metadata } from "next";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "ファクタリング業者の口コミ一覧",
  description:
    "ファクタリングを実際に利用した方のリアルな口コミを掲載。業者選びの参考にしてください。",
};

export default async function ReviewsPage() {
  const reviews = await prisma.review.findMany({
    where: { isApproved: true },
    orderBy: { createdAt: "desc" },
    include: { company: { select: { name: true, slug: true } } },
  });

  return (
    <div className="max-w-4xl mx-auto px-4 py-10">
      <h1 className="text-2xl md:text-3xl font-bold text-navy mb-2">
        口コミ一覧
      </h1>
      <p className="text-gray-500 mb-8">
        ファクタリングを実際に利用した方のリアルな口コミ・評判を掲載しています
      </p>

      {reviews.length > 0 ? (
        <div className="space-y-4">
          {reviews.map((review) => (
            <div
              key={review.id}
              className="bg-white border border-gray-200 rounded-xl p-5"
            >
              <div className="flex flex-col sm:flex-row sm:items-center gap-2 mb-3">
                <a
                  href={`/companies/${review.company.slug}`}
                  className="text-sm font-bold text-navy hover:underline"
                >
                  {review.company.name}
                </a>
                <div className="flex items-center gap-2">
                  <Stars rating={review.rating} />
                  <span className="text-xs text-gray-400">
                    {review.createdAt.toLocaleDateString("ja-JP")}
                  </span>
                </div>
              </div>
              <h3 className="font-bold text-gray-800 mb-2">{review.title}</h3>
              <p className="text-sm text-gray-600 leading-relaxed">{review.body}</p>
              {review.userType && (
                <p className="text-xs text-gray-400 mt-3">
                  投稿者: {review.userType}
                </p>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-16 bg-gray-50 rounded-xl">
          <p className="text-gray-500 mb-4">まだ口コミがありません</p>
          <a
            href="/companies"
            className="text-navy font-bold hover:underline"
          >
            業者一覧から口コミを投稿する →
          </a>
        </div>
      )}
    </div>
  );
}
