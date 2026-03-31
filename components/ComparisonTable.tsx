import Link from "next/link";
import { Stars } from "./CompanyCard";

type CompanyRow = {
  slug: string;
  name: string;
  fee: string | null;
  depositSpeed: string | null;
  rating: number | null;
  reviewCount: number;
  minAmount: number | null;
  maxAmount: number | null;
  targetBusiness: string | null;
  affiliateUrl: string | null;
};

export function ComparisonTable({ companies }: { companies: CompanyRow[] }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200 shadow-sm">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="bg-gradient-to-r from-primary to-primary-light text-white">
            <th className="px-4 py-3.5 text-left font-bold sticky left-0 bg-primary z-10">業者名</th>
            <th className="px-4 py-3.5 text-center font-bold whitespace-nowrap">評価</th>
            <th className="px-4 py-3.5 text-center font-bold whitespace-nowrap">手数料</th>
            <th className="px-4 py-3.5 text-center font-bold whitespace-nowrap">入金速度</th>
            <th className="px-4 py-3.5 text-center font-bold whitespace-nowrap">買取金額</th>
            <th className="px-4 py-3.5 text-center font-bold whitespace-nowrap">対象</th>
            <th className="px-4 py-3.5 text-center font-bold whitespace-nowrap">詳細</th>
          </tr>
        </thead>
        <tbody>
          {companies.map((c, i) => {
            const isFirst = i === 0;
            const rowBg = isFirst
              ? "bg-amber-50/60"
              : i % 2 === 0
                ? "bg-white"
                : "bg-gray-50";
            const stickyBg = isFirst
              ? "bg-amber-50"
              : i % 2 === 0
                ? "bg-white"
                : "bg-gray-50";
            return (
              <tr key={c.slug} className={`${rowBg} ${isFirst ? "border-l-4 border-l-amber-400" : ""} hover:bg-primary/5 transition-colors`}>
                <td className={`px-4 py-3 font-bold text-primary-darker sticky left-0 z-10 ${stickyBg}`}>
                  <div className="flex items-center gap-2">
                    {isFirst && (
                      <span className="inline-flex items-center justify-center w-5 h-5 bg-amber-400 text-amber-900 rounded-full text-[10px] font-black shrink-0">1</span>
                    )}
                    <Link href={`/companies/${c.slug}`} className="hover:underline hover:text-primary transition-colors">
                      {c.name}
                    </Link>
                  </div>
                </td>
                <td className="px-4 py-3 text-center">
                  {c.rating ? (
                    <div className="flex flex-col items-center">
                      <Stars rating={c.rating} />
                      <span className="text-xs mt-1 font-medium text-gray-600">{c.rating.toFixed(1)} ({c.reviewCount}件)</span>
                    </div>
                  ) : (
                    <span className="text-gray-300">-</span>
                  )}
                </td>
                <td className="px-4 py-3 text-center font-bold text-primary whitespace-nowrap">{c.fee || <span className="text-gray-300">-</span>}</td>
                <td className="px-4 py-3 text-center whitespace-nowrap font-medium">{c.depositSpeed || <span className="text-gray-300">-</span>}</td>
                <td className="px-4 py-3 text-center whitespace-nowrap">
                  {c.minAmount || c.maxAmount
                    ? `${c.minAmount ? c.minAmount + "万" : "下限なし"}〜${c.maxAmount ? c.maxAmount + "万" : "上限なし"}`
                    : "制限なし"}
                </td>
                <td className="px-4 py-3 text-center text-xs">{c.targetBusiness || <span className="text-gray-300">-</span>}</td>
                <td className="px-4 py-3 text-center">
                  <Link
                    href={`/companies/${c.slug}`}
                    className="inline-block text-xs bg-cta text-white px-4 py-2 rounded-lg font-bold hover:bg-cta-dark transition-colors whitespace-nowrap shadow-sm"
                  >
                    詳細 &rarr;
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
