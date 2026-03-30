import { prisma } from "@/lib/prisma";
import { revalidatePath } from "next/cache";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "業者管理",
  robots: { index: false, follow: false },
};

async function updateCompany(formData: FormData) {
  "use server";
  const id = parseInt(formData.get("id") as string);
  const rankingOrder = formData.get("rankingOrder")
    ? parseInt(formData.get("rankingOrder") as string)
    : null;
  const affiliateUrl = (formData.get("affiliateUrl") as string) || null;
  const isRecommended = formData.get("isRecommended") === "on";

  await prisma.company.update({
    where: { id },
    data: { rankingOrder, affiliateUrl, isRecommended },
  });

  revalidatePath("/admin/companies");
}

export default async function AdminCompaniesPage() {
  const companies = await prisma.company.findMany({
    orderBy: { rankingOrder: "asc" },
  });

  return (
    <div className="max-w-4xl mx-auto px-4 py-10">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold text-navy">業者管理</h1>
        <a href="/admin" className="text-sm text-navy hover:underline">
          ← 管理画面に戻る
        </a>
      </div>

      <div className="space-y-4">
        {companies.map((company) => (
          <form
            key={company.id}
            action={updateCompany}
            className="bg-white border border-gray-200 rounded-xl p-5"
          >
            <input type="hidden" name="id" value={company.id} />
            <div className="flex items-center gap-4 mb-3">
              <h3 className="font-bold text-navy text-lg">{company.name}</h3>
              <span className="text-xs text-gray-400">/{company.slug}</span>
            </div>

            <div className="grid md:grid-cols-3 gap-4 mb-4">
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">
                  ランキング順位
                </label>
                <input
                  type="number"
                  name="rankingOrder"
                  defaultValue={company.rankingOrder ?? ""}
                  min={1}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">
                  アフィリエイトURL
                </label>
                <input
                  type="url"
                  name="affiliateUrl"
                  defaultValue={company.affiliateUrl ?? ""}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                  placeholder="https://..."
                />
              </div>
              <div className="flex items-end gap-4">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    name="isRecommended"
                    defaultChecked={company.isRecommended}
                    className="rounded"
                  />
                  おすすめ
                </label>
                <button
                  type="submit"
                  className="bg-navy text-white px-4 py-2 rounded-lg text-sm font-bold hover:bg-navy-light transition-colors"
                >
                  保存
                </button>
              </div>
            </div>
          </form>
        ))}
      </div>
    </div>
  );
}
