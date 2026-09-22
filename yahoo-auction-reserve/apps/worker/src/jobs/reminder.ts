import { Prisma, prisma } from "@yar/db";
import { formatJstTime, formatRemaining } from "@yar/shared";
import { notifyUser } from "../notify";
import { yahooNow } from "../time";

// 終了N分前のリマインド(設計追補 2026-08-25)。
//
// スケジューラの走査から呼ばれる。BullMQ の遅延ジョブにしていないのは、
// 自動延長で endAt が動くたびにジョブを入れ直す必要があり、入れ直しに
// 失敗したときに「通知が来ないだけ」で誰も気づけないため。
// DB を毎回見る方式なら、走査が動いている限り自己修復する。
//
// 二重送信は ReminderSent の複合ユニーク(予約 x 分 x 終了時刻)で防ぐ。
// 「送ったフラグ」を予約側に持たせると、延長で終了時刻が動いたときに
// 送り直せない(古い終了時刻に対する送信済みが残り続ける)。

/** 走査1回あたりに送るリマインドの上限。詰まったときに一気に爆撃しない */
const MAX_PER_SCAN = 50;

export async function runReminderSweep(): Promise<number> {
  const settings = await prisma.notificationSetting.findMany({
    where: { NOT: { remindMinutesBefore: { isEmpty: true } } },
    select: { userId: true, remindMinutesBefore: true },
  });
  if (settings.length === 0) return 0;

  const now = yahooNow();
  let sent = 0;

  for (const setting of settings) {
    const minutesList = [...new Set(setting.remindMinutesBefore)].filter((m) => m > 0);
    if (minutesList.length === 0) continue;

    const maxMinutes = Math.max(...minutesList);
    const reservations = await prisma.bidReservation.findMany({
      where: {
        userId: setting.userId,
        status: { in: ["SCHEDULED", "MONITORING"] },
        endAt: { gt: now, lte: new Date(now.getTime() + maxMinutes * 60_000) },
      },
    });

    for (const r of reservations) {
      const remainingMs = r.endAt.getTime() - now.getTime();
      for (const minutes of minutesList) {
        // 「N分前を過ぎた」だけを条件にすると、走査が止まっていた間に
        // 通り過ぎた分まで一斉に飛ぶ。既に終了間近のものは対象外にする。
        if (remainingMs > minutes * 60_000) continue;
        if (sent >= MAX_PER_SCAN) return sent;

        try {
          await prisma.reminderSent.create({
            data: { reservationId: r.id, minutesBefore: minutes, endAt: r.endAt },
          });
        } catch (err) {
          // P2002 = 送信済み。それ以外は本当の失敗なので黙らせない
          if (
            err instanceof Prisma.PrismaClientKnownRequestError &&
            err.code === "P2002"
          ) {
            continue;
          }
          console.error(`[reminder] ${r.id} の記録に失敗:`, err);
          continue;
        }

        await notifyUser(r.userId, "REMINDER", {
          title: r.title,
          url: r.auctionUrl,
          minutesBefore: `あと ${formatRemaining(remainingMs)}(${minutes}分前の通知)`,
          endAt: formatJstTime(r.endAt),
          currentPrice: r.currentPrice ?? undefined,
          maxBidAmount: r.maxBidAmount,
        });
        sent += 1;
      }
    }
  }

  return sent;
}
