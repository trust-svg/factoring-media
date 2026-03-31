import Link from "next/link";
import { Stars } from "./CompanyCard";

type RankingCompany = {
  slug: string;
  name: string;
  description: string;
  fee: string | null;
  depositSpeed: string | null;
  rating: number | null;
  reviewCount: number;
  features: string[];
  pros: string[];
  affiliateUrl: string | null;
  rankingOrder: number | null;
};

const headerColors = [
  "bg-gradient-to-r from-amber-400 to-amber-300 text-amber-900",
  "bg-gradient-to-r from-gray-300 to-gray-200 text-gray-700",
  "bg-gradient-to-r from-amber-600 to-amber-500 text-white",
];

const medalColors = [
  { bg: "bg-amber-400", text: "text-amber-900" },
  { bg: "bg-gray-300", text: "text-gray-700" },
  { bg: "bg-amber-600", text: "text-amber-100" },
];

export function RankingTable({ companies }: { companies: RankingCompany[] }) {
  return (
    <div className="space-y-6">
      {companies.map((c, i) => {
        const isTop3 = i < 3;
        const borderColor = isTop3
          ? i === 0
            ? "border-amber-400"
            : i === 1
              ? "border-gray-300"
              : "border-amber-600"
          : "border-gray-200";

        return (
          <div
            key={c.slug}
            className={`bg-white border-2 rounded-xl overflow-hidden card-hover ${borderColor}`}
          >
            <div className={`px-5 py-3 flex items-center gap-3 ${
              isTop3 ? headerColors[i] : "bg-gray-50"
            }`}>
              {isTop3 ? (
                <div className={`w-10 h-10 ${medalColors[i].bg} rounded-full flex items-center justify-center shadow-md`}>
                  <span className={`text-sm font-black ${medalColors[i].text}`}>
                    {i + 1}
                  </span>
                </div>
              ) : (
                <div className="w-10 h-10 bg-primary/10 rounded-full flex items-center justify-center">
                  <span className="text-sm font-bold text-primary">
                    {c.rankingOrder || i + 1}
                  </span>
                </div>
              )}
              <h3 className={`text-lg font-bold flex-1 ${isTop3 ? "" : "text-primary-darker"}`}>{c.name}</h3>
              {c.rating && (
                <div className="flex items-center gap-1">
                  <Stars rating={c.rating} />
                  <span className="font-bold text-sm">{c.rating.toFixed(1)}</span>
                </div>
              )}
            </div>
            <div className="p-5">
              <p className="text-sm text-gray-600 mb-4">{c.description}</p>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                <div className="bg-primary/5 rounded-lg px-3 py-2.5 text-center">
                  <div className="flex items-center justify-center gap-1 mb-1">
                    <svg className="w-3.5 h-3.5 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span className="text-xs text-gray-400">手数料</span>
                  </div>
                  <span className="font-bold text-primary text-sm">{c.fee || "-"}</span>
                </div>
                <div className="bg-secondary/5 rounded-lg px-3 py-2.5 text-center">
                  <div className="flex items-center justify-center gap-1 mb-1">
                    <svg className="w-3.5 h-3.5 text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    <span className="text-xs text-gray-400">入金速度</span>
                  </div>
                  <span className="font-bold text-secondary text-sm">{c.depositSpeed || "-"}</span>
                </div>
                <div className="bg-green/5 rounded-lg px-3 py-2.5 text-center">
                  <div className="flex items-center justify-center gap-1 mb-1">
                    <svg className="w-3.5 h-3.5 text-green" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8h2a2 2 0 012 2v6a2 2 0 01-2 2h-2v4l-4-4H9a1.994 1.994 0 01-1.414-.586m0 0L11 14h4a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2v4l.586-.586z" />
                    </svg>
                    <span className="text-xs text-gray-400">口コミ数</span>
                  </div>
                  <span className="font-bold text-green text-sm">{c.reviewCount}件</span>
                </div>
                <div className="bg-accent/5 rounded-lg px-3 py-2.5 text-center">
                  <div className="flex items-center justify-center gap-1 mb-1">
                    <svg className="w-3.5 h-3.5 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
                    </svg>
                    <span className="text-xs text-gray-400">特徴</span>
                  </div>
                  <span className="font-bold text-accent-dark text-xs">{c.features[0] || "-"}</span>
                </div>
              </div>

              <div className="mb-4">
                <h4 className="text-xs font-bold text-gray-500 mb-2 flex items-center gap-1">
                  <svg className="w-3.5 h-3.5 text-green" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  メリット
                </h4>
                <ul className="text-sm text-gray-600 space-y-1.5">
                  {c.pros.slice(0, 3).map((pro) => (
                    <li key={pro} className="flex items-start gap-2">
                      <span className="text-green shrink-0 mt-0.5 font-bold">&#10003;</span>
                      {pro}
                    </li>
                  ))}
                </ul>
              </div>

              <div className="flex gap-3">
                <Link
                  href={`/companies/${c.slug}`}
                  className="flex-1 text-center text-sm border-2 border-primary text-primary py-2.5 rounded-lg font-bold hover:bg-primary hover:text-white transition-colors"
                >
                  詳細を見る
                </Link>
                <a
                  href={c.affiliateUrl || "/estimate"}
                  target={c.affiliateUrl ? "_blank" : undefined}
                  rel={c.affiliateUrl ? "noopener noreferrer nofollow" : undefined}
                  className="flex-1 text-center text-sm bg-cta text-white py-2.5 rounded-lg font-bold hover:bg-cta-dark transition-colors shadow-md pulse-cta"
                >
                  {c.affiliateUrl ? "公式サイトへ \u2192" : "無料見積もり \u2192"}
                </a>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
