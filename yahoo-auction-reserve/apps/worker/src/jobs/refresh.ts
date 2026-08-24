import type { Job } from "bullmq";
import { Prisma, prisma } from "@yar/db";
import { fetchAuctionInfo } from "@yar/shared";
import type { ReservationJobData } from "../queues";
import { notifyUser } from "../notify";

// 商品情報の軽量リフレッシュ(設計 §7.1)
// - 現在価格・終了時刻・早期終了の反映
// - 現在価格が上限額を超えたら EXPIRED にして通知(無駄なブラウザ起動を防ぐ)
export async function runRefreshJob(job: Job<ReservationJobData>): Promise<void> {
  const reservation = await prisma.bidReservation.findUnique({
    where: { id: job.data.reservationId },
  });
  if (!reservation || reservation.status !== "SCHEDULED") return;

  const info = await fetchAuctionInfo(reservation.auctionUrl);

  const data: Prisma.BidReservationUpdateInput = { priceCheckedAt: new Date() };
  if (info.currentPrice !== undefined) data.currentPrice = info.currentPrice;
  if (info.endAt) data.endAt = info.endAt;

  if (info.isClosed) {
    await prisma.bidReservation.update({
      where: { id: reservation.id },
      data: { ...data, status: "EXPIRED", failureReason: "AUCTION_CLOSED_EARLY" },
    });
    await notifyUser(reservation.userId, "EXPIRED", {
      title: reservation.title,
      url: reservation.auctionUrl,
      reason: "オークションが終了(または取り消し)されていました",
    });
    return;
  }

  if (
    info.currentPrice !== undefined &&
    info.currentPrice >= reservation.maxBidAmount
  ) {
    await prisma.bidReservation.update({
      where: { id: reservation.id },
      data: { ...data, status: "EXPIRED", failureReason: "PRICE_OVER_LIMIT" },
    });
    await notifyUser(reservation.userId, "EXPIRED", {
      title: reservation.title,
      url: reservation.auctionUrl,
      currentPrice: info.currentPrice,
      maxBidAmount: reservation.maxBidAmount,
      reason: "現在価格が上限額に達したため入札をスキップします",
    });
    return;
  }

  await prisma.bidReservation.update({
    where: { id: reservation.id },
    data,
  });
}
