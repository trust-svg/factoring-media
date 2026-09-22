import type { Job } from "bullmq";
import { Prisma, prisma } from "@yar/db";
import { fetchAuctionInfo } from "@yar/shared";
import type { ReservationJobData } from "../queues";
import { notifyUser } from "../notify";
import { tryAutoRaise } from "../autoRaise";

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

  // 判断材料は「まだ入っていないときだけ」埋める。毎回上書きすると、
  // パーサが壊れた回の undefined で既に取れていた値を潰しかねない。
  // 即決価格は出品者が途中で下げる/取り下げることがあるので、
  // 取れたときは毎回上書きする(他の判断材料と扱いが違う)。取れなかった
  // 回に null で潰すと「即決なし」に化けるので、undefined は触らない。
  if (info.buyNowPrice !== undefined) data.buyNowPrice = info.buyNowPrice;
  if (reservation.shippingFee === null && info.shippingFee !== undefined) {
    data.shippingFee = info.shippingFee;
  }
  if (reservation.shippingNote === null && info.shippingNote !== undefined) {
    data.shippingNote = info.shippingNote;
  }
  if (reservation.sellerRating === null && info.sellerRating !== undefined) {
    data.sellerRating = info.sellerRating;
  }
  if (reservation.sellerRatingCount === null && info.sellerRatingCount !== undefined) {
    data.sellerRatingCount = info.sellerRatingCount;
  }

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
    // 先に価格を書いてから増額を判断する。承認ボタンを押した側は
    // reservation.currentPrice を見て「承認額で足りるか」を検証するので、
    // 古い価格のまま聞くと足りない額を承認させてしまう。
    await prisma.bidReservation.update({ where: { id: reservation.id }, data });

    // 増額はここ(価格更新の時点)で聞く。入札直前では人間が答える時間が無い。
    const outcome = await tryAutoRaise({ ...reservation, currentPrice: info.currentPrice }, info.currentPrice, {
      allowApproval: true,
    });
    if (outcome.kind === "RAISED") return; // 上限を上げたので予約は生かす
    if (outcome.kind === "APPROVAL_PENDING") return; // 返事を待つ間は SCHEDULED のまま
    if (outcome.reason === "ALREADY_PENDING") return; // 前回の問い合わせが継続中

    await prisma.bidReservation.update({
      where: { id: reservation.id },
      data: { status: "EXPIRED", failureReason: "PRICE_OVER_LIMIT" },
    });
    await notifyUser(reservation.userId, "EXPIRED", {
      title: reservation.title,
      url: reservation.auctionUrl,
      currentPrice: info.currentPrice,
      maxBidAmount: reservation.maxBidAmount,
      reason: `現在価格が上限額に達したため入札をスキップします(${outcome.message})`,
    });
    return;
  }

  await prisma.bidReservation.update({
    where: { id: reservation.id },
    data,
  });
}
