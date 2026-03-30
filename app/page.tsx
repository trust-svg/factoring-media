import { prisma } from "@/lib/prisma";
import { CompanyCard } from "@/components/CompanyCard";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const topCompanies = await prisma.company.findMany({
    where: { isRecommended: true },
    orderBy: { rankingOrder: "asc" },
    take: 3,
  });

  const latestReviews = await prisma.review.findMany({
    where: { isApproved: true },
    orderBy: { createdAt: "desc" },
    take: 3,
    include: { company: { select: { name: true, slug: true } } },
  });

  return (
    <>
      {/* Hero */}
      <section className="bg-gradient-to-br from-navy via-navy-light to-navy text-white py-16 md:py-24">
        <div className="max-w-4xl mx-auto px-4 text-center">
          <h1 className="text-3xl md:text-5xl font-black leading-tight mb-6">
            ファクタリング業者を
            <br />
            <span className="text-green">口コミ・評判</span>で徹底比較
          </h1>
          <p className="text-lg md:text-xl text-gray-300 mb-8 max-w-2xl mx-auto">
            手数料・入金速度・審査基準をリアルな口コミで比較。
            <br className="hidden md:block" />
            あなたに最適なファクタリング業者が見つかります。
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <a
              href="/estimate"
              className="bg-green hover:bg-green-dark text-white px-8 py-4 rounded-xl text-lg font-bold transition-colors shadow-lg"
            >
              無料で一括見積もり
            </a>
            <a
              href="/ranking"
              className="bg-white/10 hover:bg-white/20 text-white px-8 py-4 rounded-xl text-lg font-medium transition-colors border border-white/20"
            >
              おすすめランキングを見る
            </a>
          </div>
          <p className="text-sm text-gray-400 mt-4">
            ※ 完全無料・最短30秒で入力完了
          </p>
        </div>
      </section>

      {/* Top 3 Ranking */}
      <section className="max-w-6xl mx-auto px-4 py-16">
        <div className="text-center mb-10">
          <h2 className="text-2xl md:text-3xl font-bold text-navy mb-3">
            おすすめファクタリング業者 TOP3
          </h2>
          <p className="text-gray-500">
            2026年3月最新版 — 口コミ・手数料・入金速度を総合評価
          </p>
        </div>
        <div className="grid md:grid-cols-3 gap-6">
          {topCompanies.map((company) => (
            <CompanyCard key={company.slug} {...company} />
          ))}
        </div>
        <div className="text-center mt-8">
          <a
            href="/ranking"
            className="text-navy font-bold hover:underline"
          >
            全ランキングを見る →
          </a>
        </div>
      </section>

      {/* What is Factoring */}
      <section className="bg-gray-50 py-16">
        <div className="max-w-4xl mx-auto px-4">
          <h2 className="text-2xl font-bold text-navy mb-6 text-center">
            ファクタリングとは？
          </h2>
          <div className="bg-white rounded-xl p-6 md:p-8 shadow-sm">
            <p className="text-gray-700 leading-relaxed mb-4">
              ファクタリングとは、企業が保有する売掛金（請求書）をファクタリング会社に売却して、支払期日前に現金化する資金調達方法です。
              融資とは異なり<strong>借入ではない</strong>ため、信用情報に影響せず、最短即日で資金を得ることができます。
            </p>
            <div className="grid md:grid-cols-3 gap-4 mt-6">
              <div className="bg-green/5 rounded-lg p-4 text-center">
                <div className="text-3xl mb-2">&#128176;</div>
                <h3 className="font-bold text-navy mb-1">最短即日入金</h3>
                <p className="text-sm text-gray-600">申込みから最短即日で現金化</p>
              </div>
              <div className="bg-green/5 rounded-lg p-4 text-center">
                <div className="text-3xl mb-2">&#128196;</div>
                <h3 className="font-bold text-navy mb-1">借入ではない</h3>
                <p className="text-sm text-gray-600">信用情報に影響なし</p>
              </div>
              <div className="bg-green/5 rounded-lg p-4 text-center">
                <div className="text-3xl mb-2">&#128170;</div>
                <h3 className="font-bold text-navy mb-1">赤字でもOK</h3>
                <p className="text-sm text-gray-600">売掛先の信用力で審査</p>
              </div>
            </div>
            <div className="text-center mt-6">
              <a href="/articles/what-is-factoring" className="text-navy font-medium hover:underline">
                ファクタリングについてもっと詳しく →
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* Latest Reviews */}
      {latestReviews.length > 0 && (
        <section className="max-w-6xl mx-auto px-4 py-16">
          <h2 className="text-2xl font-bold text-navy mb-8 text-center">
            最新の口コミ
          </h2>
          <div className="grid md:grid-cols-3 gap-6">
            {latestReviews.map((review) => (
              <div key={review.id} className="bg-white border border-gray-200 rounded-xl p-5">
                <div className="flex items-center gap-2 mb-2">
                  <div className="flex text-star">
                    {Array.from({ length: review.rating }).map((_, i) => (
                      <span key={i}>&#9733;</span>
                    ))}
                  </div>
                  <span className="text-xs text-gray-400">
                    {review.createdAt.toLocaleDateString("ja-JP")}
                  </span>
                </div>
                <h3 className="font-bold text-navy mb-1">{review.title}</h3>
                <p className="text-sm text-gray-600 line-clamp-3 mb-3">{review.body}</p>
                <a
                  href={`/companies/${review.company.slug}`}
                  className="text-sm text-navy font-medium hover:underline"
                >
                  {review.company.name}の詳細 →
                </a>
              </div>
            ))}
          </div>
          <div className="text-center mt-8">
            <a href="/reviews" className="text-navy font-bold hover:underline">
              すべての口コミを見る →
            </a>
          </div>
        </section>
      )}

      {/* CTA Banner */}
      <section className="bg-navy py-16">
        <div className="max-w-3xl mx-auto px-4 text-center text-white">
          <h2 className="text-2xl md:text-3xl font-bold mb-4">
            どのファクタリング業者が最適か分からない方へ
          </h2>
          <p className="text-gray-300 mb-8">
            30秒の簡単入力で、あなたの条件に合った業者を無料でご紹介します
          </p>
          <a
            href="/estimate"
            className="inline-block bg-green hover:bg-green-dark text-white px-10 py-4 rounded-xl text-lg font-bold transition-colors shadow-lg"
          >
            無料で一括見積もりする
          </a>
        </div>
      </section>
    </>
  );
}
