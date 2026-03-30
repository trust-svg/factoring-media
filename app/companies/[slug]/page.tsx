import { prisma } from "@/lib/prisma";
import { notFound } from "next/navigation";
import { Stars } from "@/components/CompanyCard";
import { ReviewForm } from "@/components/ReviewForm";
import { generateCompanyJsonLd } from "@/lib/seo";
import type { Metadata } from "next";

type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const company = await prisma.company.findUnique({ where: { slug } });
  if (!company) return {};

  return {
    title: `${company.name}の口コミ・評判 | 手数料・入金速度を徹底解説`,
    description: `${company.name}のリアルな口コミ・評判を掲載。手数料${company.fee || "要問合せ"}、入金速度${company.depositSpeed || "要問合せ"}。メリット・デメリットを徹底解説。`,
  };
}

export const dynamic = "force-dynamic";

export default async function CompanyDetailPage({ params }: Props) {
  const { slug } = await params;
  const company = await prisma.company.findUnique({
    where: { slug },
    include: {
      reviews: {
        where: { isApproved: true },
        orderBy: { createdAt: "desc" },
      },
    },
  });

  if (!company) notFound();

  const jsonLd = generateCompanyJsonLd(company);

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />

      <div className="max-w-4xl mx-auto px-4 py-10">
        {/* Breadcrumb */}
        <nav className="text-sm text-gray-400 mb-6">
          <a href="/" className="hover:text-navy">ホーム</a>
          <span className="mx-2">/</span>
          <a href="/companies" className="hover:text-navy">業者一覧</a>
          <span className="mx-2">/</span>
          <span className="text-gray-600">{company.name}</span>
        </nav>

        {/* Header */}
        <div className="bg-white border border-gray-200 rounded-xl p-6 mb-8">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-4">
            <div>
              {company.isRecommended && (
                <span className="inline-block bg-green text-white text-xs font-bold px-3 py-1 rounded-full mb-2">
                  おすすめ
                </span>
              )}
              <h1 className="text-2xl md:text-3xl font-bold text-navy">
                {company.name}
              </h1>
            </div>
            {company.rating && (
              <div className="flex items-center gap-2">
                <Stars rating={company.rating} size="lg" />
                <span className="text-2xl font-bold text-navy">
                  {company.rating.toFixed(1)}
                </span>
                <span className="text-sm text-gray-400">
                  ({company.reviewCount}件の口コミ)
                </span>
              </div>
            )}
          </div>
          <p className="text-gray-700 leading-relaxed">{company.description}</p>
        </div>

        {/* Basic Info */}
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden mb-8">
          <h2 className="bg-navy text-white font-bold px-6 py-3">基本情報</h2>
          <table className="w-full text-sm">
            <tbody>
              {[
                ["手数料", company.fee],
                ["入金速度", company.depositSpeed],
                ["買取金額", company.minAmount || company.maxAmount
                  ? `${company.minAmount ? company.minAmount + "万円" : "下限なし"} 〜 ${company.maxAmount ? company.maxAmount + "万円" : "上限なし"}`
                  : "制限なし"],
                ["対象事業者", company.targetBusiness],
                ["公式サイト", company.officialUrl],
              ].map(([label, value]) => (
                <tr key={label as string} className="border-b border-gray-100">
                  <th className="px-6 py-3 text-left text-gray-500 bg-gray-50 w-32 font-medium">
                    {label}
                  </th>
                  <td className="px-6 py-3 text-gray-800">
                    {label === "公式サイト" ? (
                      <a
                        href={value as string}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-navy hover:underline"
                      >
                        {value}
                      </a>
                    ) : (
                      (value as string) || "ー"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Features */}
        {company.features.length > 0 && (
          <div className="mb-8">
            <h2 className="text-xl font-bold text-navy mb-4">特徴</h2>
            <div className="flex flex-wrap gap-2">
              {company.features.map((f) => (
                <span key={f} className="bg-navy/5 text-navy px-4 py-2 rounded-full text-sm font-medium">
                  {f}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Pros / Cons */}
        <div className="grid md:grid-cols-2 gap-6 mb-8">
          <div className="bg-green/5 border border-green/20 rounded-xl p-5">
            <h3 className="font-bold text-green-dark mb-3 flex items-center gap-2">
              <span>&#9675;</span> メリット
            </h3>
            <ul className="space-y-2">
              {company.pros.map((pro) => (
                <li key={pro} className="text-sm text-gray-700 flex items-start gap-2">
                  <span className="text-green shrink-0 mt-0.5">&#10003;</span>
                  {pro}
                </li>
              ))}
            </ul>
          </div>
          <div className="bg-warning/5 border border-warning/20 rounded-xl p-5">
            <h3 className="font-bold text-warning mb-3 flex items-center gap-2">
              <span>&#9651;</span> デメリット
            </h3>
            <ul className="space-y-2">
              {company.cons.map((con) => (
                <li key={con} className="text-sm text-gray-700 flex items-start gap-2">
                  <span className="text-warning shrink-0 mt-0.5">&#9888;</span>
                  {con}
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* CTA */}
        <div className="bg-green/10 border border-green rounded-xl p-6 text-center mb-8">
          <p className="text-lg font-bold text-navy mb-3">
            {company.name}に申し込む
          </p>
          <a
            href={company.affiliateUrl || company.officialUrl}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="inline-block bg-green text-white px-10 py-4 rounded-xl text-lg font-bold hover:bg-green-dark transition-colors shadow-lg"
          >
            公式サイトを見る（無料）
          </a>
        </div>

        {/* Reviews */}
        <div className="mb-8">
          <h2 className="text-xl font-bold text-navy mb-6">
            口コミ・評判 ({company.reviews.length}件)
          </h2>
          {company.reviews.length > 0 ? (
            <div className="space-y-4">
              {company.reviews.map((review) => (
                <div key={review.id} className="bg-white border border-gray-200 rounded-xl p-5">
                  <div className="flex items-center gap-3 mb-2">
                    <Stars rating={review.rating} />
                    <span className="font-bold text-navy">{review.title}</span>
                  </div>
                  <p className="text-sm text-gray-600 mb-2">{review.body}</p>
                  <div className="flex items-center gap-3 text-xs text-gray-400">
                    {review.userType && <span>{review.userType}</span>}
                    <span>{review.createdAt.toLocaleDateString("ja-JP")}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-500 text-center py-8">
              まだ口コミがありません。最初の口コミを投稿しませんか？
            </p>
          )}
        </div>

        {/* Review Form */}
        <ReviewForm companyId={company.id} companyName={company.name} />
      </div>
    </>
  );
}
