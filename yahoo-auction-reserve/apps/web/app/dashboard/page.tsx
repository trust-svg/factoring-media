import Link from "next/link";
import { redirect } from "next/navigation";
import { prisma } from "@yar/db";
import { getSessionUser } from "@/lib/auth";
import ReservationList, { type ReservationItem } from "./ReservationList";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const user = await getSessionUser();
  if (!user) redirect("/login");

  const reservations = await prisma.bidReservation.findMany({
    where: { userId: user.id },
    orderBy: { endAt: "asc" },
    include: { group: { select: { name: true } } },
  });

  // Date をそのままクライアントコンポーネントへ渡すと、シリアライズを経て
  // 文字列になる場所とならない場所が混ざる。境界でミリ秒に落として型で固定する。
  const items: ReservationItem[] = reservations.map((r) => ({
    id: r.id,
    title: r.title,
    imageUrl: r.imageUrl,
    endAtMs: r.endAt.getTime(),
    status: r.status,
    dryRun: r.dryRun,
    currentPrice: r.currentPrice,
    maxBidAmount: r.maxBidAmount,
    absoluteMaxAmount: r.absoluteMaxAmount,
    autoRaiseMode: r.autoRaiseMode,
    snipeSecondsBefore: r.snipeSecondsBefore,
    hasAutoExtension: r.hasAutoExtension,
    failureReason: r.failureReason,
    resultPrice: r.resultPrice,
    groupName: r.group?.name ?? null,
    shippingFee: r.shippingFee,
    sellerRating: r.sellerRating,
    marketMedianPrice: r.marketMedianPrice,
    marketSampleCount: r.marketSampleCount,
  }));

  return (
    <>
      <div className="page-head">
        <h1>予約一覧</h1>
        <Link href="/reservations/new">
          <button>新規予約</button>
        </Link>
      </div>
      <ReservationList items={items} initialNowMs={Date.now()} />
    </>
  );
}
