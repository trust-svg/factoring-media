import { prisma } from "@yar/db";
import { notifyUser } from "./notify";
import { yahooNow } from "./time";

// グループ予約: 同じグループの1件を落札したら、残りを取りやめる。
// 「同じレンズをA店・B店・C店で押さえたが、欲しいのは1本」という使い方。
//
// キャンセルするのは **まだ入札が確定していないもの** だけ。既に BIDDING に
// 入っているものは、こちらが取り消しても向こうで入札が成立している可能性が
// あり、取り消せたつもりで二重に落札する。BIDDING は触らずに報告だけする。
export async function cancelGroupSiblings(
  wonReservationId: string,
): Promise<{ cancelled: number; skipped: number }> {
  const won = await prisma.bidReservation.findUnique({
    where: { id: wonReservationId },
    include: { group: true },
  });
  if (!won?.groupId || !won.group?.cancelOthersOnWin) return { cancelled: 0, skipped: 0 };

  const siblings = await prisma.bidReservation.findMany({
    where: {
      groupId: won.groupId,
      id: { not: won.id },
      status: { in: ["SCHEDULED", "MONITORING", "BIDDING"] },
    },
  });

  let cancelled = 0;
  let skipped = 0;
  for (const s of siblings) {
    if (s.status === "BIDDING") {
      // 取り消せない。黙って残すと「グループなのに2つ落札した」の原因が
      // 追えなくなるので、必ず記録と通知に出す。
      skipped += 1;
      console.warn(
        `[group] ${s.id} は入札実行中のため取りやめられませんでした(二重落札の可能性あり)`,
      );
      await notifyUser(s.userId, "FAILED", {
        title: s.title,
        url: s.auctionUrl,
        groupName: won.group.name,
        reason:
          "同じグループの他の商品を落札しましたが、この予約は入札実行中で取りやめられませんでした。結果を確認してください",
      });
      continue;
    }

    const updated = await prisma.bidReservation.updateMany({
      where: { id: s.id, status: s.status },
      data: { status: "CANCELLED", failureReason: "GROUP_CANCELLED" },
    });
    if (updated.count === 0) {
      skipped += 1;
      continue; // 直前に状態が変わった
    }
    cancelled += 1;

    await prisma.bidAttempt.create({
      data: {
        reservationId: s.id,
        scheduledFor: yahooNow(),
        executedAt: yahooNow(),
        bidAmount: s.maxBidAmount,
        outcome: "GROUP_CANCELLED",
        detail: `グループ「${won.group.name}」の ${won.title ?? won.auctionUrl} を落札したため`,
      },
    });
    await notifyUser(s.userId, "GROUP_CANCELLED", {
      title: s.title,
      url: s.auctionUrl,
      groupName: won.group.name,
      reason: `${won.title ?? "同じグループの商品"} を落札したため取りやめました`,
    });
  }

  return { cancelled, skipped };
}
