import { prisma } from "@/lib/prisma";
import { Stars } from "@/components/CompanyCard";
import { revalidatePath } from "next/cache";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "口コミ管理",
  robots: { index: false, follow: false },
};

async function approveReview(formData: FormData) {
  "use server";
  const id = parseInt(formData.get("id") as string);
  await prisma.review.update({
    where: { id },
    data: { isApproved: true },
  });

  const review = await prisma.review.findUnique({ where: { id }, select: { companyId: true } });
  if (review) {
    const count = await prisma.review.count({
      where: { companyId: review.companyId, isApproved: true },
    });
    const avg = await prisma.review.aggregate({
      where: { companyId: review.companyId, isApproved: true },
      _avg: { rating: true },
    });
    await prisma.company.update({
      where: { id: review.companyId },
      data: {
        reviewCount: count,
        rating: avg._avg.rating ? Math.round(avg._avg.rating * 10) / 10 : null,
      },
    });
  }

  revalidatePath("/admin/reviews");
}

async function deleteReview(formData: FormData) {
  "use server";
  const id = parseInt(formData.get("id") as string);
  await prisma.review.delete({ where: { id } });
  revalidatePath("/admin/reviews");
}

export default async function AdminReviewsPage() {
  const reviews = await prisma.review.findMany({
    orderBy: [{ isApproved: "asc" }, { createdAt: "desc" }],
    include: { company: { select: { name: true } } },
  });

  return (
    <div className="max-w-4xl mx-auto px-4 py-10">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold text-navy">口コミ管理</h1>
        <a href="/admin" className="text-sm text-navy hover:underline">
          ← 管理画面に戻る
        </a>
      </div>

      <div className="space-y-4">
        {reviews.map((review) => (
          <div
            key={review.id}
            className={`bg-white border rounded-xl p-5 ${
              review.isApproved ? "border-gray-200" : "border-warning/50 bg-warning/5"
            }`}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  {!review.isApproved && (
                    <span className="text-xs bg-warning text-white px-2 py-0.5 rounded">
                      未承認
                    </span>
                  )}
                  <span className="text-sm font-bold text-navy">
                    {review.company.name}
                  </span>
                  <Stars rating={review.rating} />
                </div>
                <h3 className="font-bold text-gray-800">{review.title}</h3>
                <p className="text-sm text-gray-600 mt-1">{review.body}</p>
                <div className="text-xs text-gray-400 mt-2">
                  {review.userType && <span>{review.userType} | </span>}
                  {review.createdAt.toLocaleDateString("ja-JP")}
                </div>
              </div>
              <div className="flex flex-col gap-2 shrink-0">
                {!review.isApproved && (
                  <form action={approveReview}>
                    <input type="hidden" name="id" value={review.id} />
                    <button
                      type="submit"
                      className="text-xs bg-green text-white px-3 py-1.5 rounded font-bold hover:bg-green-dark transition-colors"
                    >
                      承認
                    </button>
                  </form>
                )}
                <form action={deleteReview}>
                  <input type="hidden" name="id" value={review.id} />
                  <button
                    type="submit"
                    className="text-xs bg-gray-200 text-gray-600 px-3 py-1.5 rounded font-bold hover:bg-warning hover:text-white transition-colors"
                  >
                    削除
                  </button>
                </form>
              </div>
            </div>
          </div>
        ))}

        {reviews.length === 0 && (
          <p className="text-center text-gray-500 py-8">口コミはまだありません</p>
        )}
      </div>
    </div>
  );
}
