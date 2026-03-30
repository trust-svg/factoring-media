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

const medals = ["", "🥇", "🥈", "🥉"];

export function RankingTable({ companies }: { companies: RankingCompany[] }) {
  return (
    <div className="space-y-6">
      {companies.map((c, i) => (
        <div
          key={c.slug}
          className={`bg-white border-2 rounded-xl overflow-hidden ${
            i < 3 ? "border-star" : "border-gray-200"
          }`}
        >
          <div className={`px-5 py-3 flex items-center gap-3 ${
            i < 3 ? "bg-star/10" : "bg-gray-50"
          }`}>
            <span className="text-2xl font-black text-navy">
              {i < 3 ? medals[i + 1] : `#${c.rankingOrder || i + 1}`}
            </span>
            <h3 className="text-lg font-bold text-navy flex-1">{c.name}</h3>
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
              <div className="bg-gray-50 rounded-lg px-3 py-2 text-center">
                <span className="text-xs text-gray-400 block">手数料</span>
                <span className="font-bold text-navy text-sm">{c.fee || "-"}</span>
              </div>
              <div className="bg-gray-50 rounded-lg px-3 py-2 text-center">
                <span className="text-xs text-gray-400 block">入金速度</span>
                <span className="font-bold text-navy text-sm">{c.depositSpeed || "-"}</span>
              </div>
              <div className="bg-gray-50 rounded-lg px-3 py-2 text-center">
                <span className="text-xs text-gray-400 block">口コミ数</span>
                <span className="font-bold text-navy text-sm">{c.reviewCount}件</span>
              </div>
              <div className="bg-gray-50 rounded-lg px-3 py-2 text-center">
                <span className="text-xs text-gray-400 block">特徴</span>
                <span className="font-bold text-navy text-xs">{c.features[0] || "-"}</span>
              </div>
            </div>

            <div className="mb-4">
              <h4 className="text-xs font-bold text-gray-500 mb-1">メリット</h4>
              <ul className="text-sm text-gray-600 space-y-1">
                {c.pros.slice(0, 3).map((pro) => (
                  <li key={pro} className="flex items-start gap-1.5">
                    <span className="text-green shrink-0 mt-0.5">&#10003;</span>
                    {pro}
                  </li>
                ))}
              </ul>
            </div>

            <div className="flex gap-3">
              <Link
                href={`/companies/${c.slug}`}
                className="flex-1 text-center text-sm border border-navy text-navy py-2.5 rounded-lg font-medium hover:bg-navy hover:text-white transition-colors"
              >
                詳細を見る
              </Link>
              <a
                href={c.affiliateUrl || "/estimate"}
                target={c.affiliateUrl ? "_blank" : undefined}
                rel={c.affiliateUrl ? "noopener noreferrer nofollow" : undefined}
                className="flex-1 text-center text-sm bg-green text-white py-2.5 rounded-lg font-bold hover:bg-green-dark transition-colors"
              >
                {c.affiliateUrl ? "公式サイトを見る（無料）" : "無料見積もり"}
              </a>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
