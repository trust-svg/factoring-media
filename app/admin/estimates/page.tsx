import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "見積もり依頼一覧",
  robots: { index: false, follow: false },
};

export default async function AdminEstimatesPage() {
  const estimates = await prisma.estimateRequest.findMany({
    orderBy: { createdAt: "desc" },
  });

  return (
    <div className="max-w-4xl mx-auto px-4 py-10">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold text-navy">見積もり依頼一覧</h1>
        <a href="/admin" className="text-sm text-navy hover:underline">
          ← 管理画面に戻る
        </a>
      </div>

      {estimates.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="bg-navy text-white">
                <th className="px-4 py-3 text-left">日時</th>
                <th className="px-4 py-3 text-left">事業形態</th>
                <th className="px-4 py-3 text-right">金額(万円)</th>
                <th className="px-4 py-3 text-left">急ぎ度</th>
                <th className="px-4 py-3 text-left">メール</th>
                <th className="px-4 py-3 text-left">電話</th>
                <th className="px-4 py-3 text-left">備考</th>
              </tr>
            </thead>
            <tbody>
              {estimates.map((est, i) => (
                <tr key={est.id} className={i % 2 === 0 ? "bg-white" : "bg-gray-50"}>
                  <td className="px-4 py-3 whitespace-nowrap">
                    {est.createdAt.toLocaleDateString("ja-JP")}
                  </td>
                  <td className="px-4 py-3">{est.businessType}</td>
                  <td className="px-4 py-3 text-right font-bold">{est.invoiceAmount.toLocaleString()}</td>
                  <td className="px-4 py-3">{est.urgency}</td>
                  <td className="px-4 py-3">{est.email}</td>
                  <td className="px-4 py-3">{est.phone || "-"}</td>
                  <td className="px-4 py-3 max-w-xs truncate">{est.memo || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-center text-gray-500 py-8">見積もり依頼はまだありません</p>
      )}
    </div>
  );
}
