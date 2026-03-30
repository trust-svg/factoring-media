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
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="bg-navy text-white">
            <th className="px-4 py-3 text-left font-medium sticky left-0 bg-navy z-10">業者名</th>
            <th className="px-4 py-3 text-center font-medium whitespace-nowrap">評価</th>
            <th className="px-4 py-3 text-center font-medium whitespace-nowrap">手数料</th>
            <th className="px-4 py-3 text-center font-medium whitespace-nowrap">入金速度</th>
            <th className="px-4 py-3 text-center font-medium whitespace-nowrap">買取金額</th>
            <th className="px-4 py-3 text-center font-medium whitespace-nowrap">対象</th>
            <th className="px-4 py-3 text-center font-medium whitespace-nowrap">詳細</th>
          </tr>
        </thead>
        <tbody>
          {companies.map((c, i) => (
            <tr key={c.slug} className={i % 2 === 0 ? "bg-white" : "bg-gray-50"}>
              <td className={`px-4 py-3 font-bold text-navy sticky left-0 z-10 ${i % 2 === 0 ? "bg-white" : "bg-gray-50"}`}>
                <Link href={`/companies/${c.slug}`} className="hover:underline">
                  {c.name}
                </Link>
              </td>
              <td className="px-4 py-3 text-center">
                {c.rating ? (
                  <div className="flex flex-col items-center">
                    <Stars rating={c.rating} />
                    <span className="text-xs mt-1">{c.rating.toFixed(1)} ({c.reviewCount}件)</span>
                  </div>
                ) : "-"}
              </td>
              <td className="px-4 py-3 text-center font-bold whitespace-nowrap">{c.fee || "-"}</td>
              <td className="px-4 py-3 text-center whitespace-nowrap">{c.depositSpeed || "-"}</td>
              <td className="px-4 py-3 text-center whitespace-nowrap">
                {c.minAmount || c.maxAmount
                  ? `${c.minAmount ? c.minAmount + "万" : "下限なし"}〜${c.maxAmount ? c.maxAmount + "万" : "上限なし"}`
                  : "制限なし"}
              </td>
              <td className="px-4 py-3 text-center text-xs">{c.targetBusiness || "-"}</td>
              <td className="px-4 py-3 text-center">
                <Link
                  href={`/companies/${c.slug}`}
                  className="inline-block text-xs bg-green text-white px-3 py-1.5 rounded font-bold hover:bg-green-dark transition-colors whitespace-nowrap"
                >
                  詳細
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
