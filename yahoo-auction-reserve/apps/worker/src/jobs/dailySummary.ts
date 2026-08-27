import { prisma } from "@yar/db";
import { formatJstTime, isSameJstDay, jstDayKey } from "@yar/shared";
import { notifyUser } from "../notify";
import { yahooNow } from "../time";

// 毎日の稼働サマリ(設計追補 2026-08-25)。死活監視を兼ねる。
//
// このメッセージが **届かないこと自体が異常の合図**。したがって中身は
// 「動いています」ではなく、動いていないと出せない実物の数字で構成する:
// - 最後に価格を取得できた時刻(refresh が回っているかの実測)
// - 直近24時間で通知の送信に失敗した件数(片方の経路だけ死んでいる状態の検出)
// - ウォッチリストを最後に同期できた時刻(ヤフオクのログインが生きているかの実測)
//
// 「予約0件」と「取得できなかった」は別物なので、0 件は 0 件と書く。

function parseHhMm(s: string): { hour: number; minute: number } | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(s.trim());
  if (!m) return null;
  const hour = Number(m[1]);
  const minute = Number(m[2]);
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;
  return { hour, minute };
}

/** JST における、その日の指定時刻(UTC の Date として返す) */
function jstTimeToday(now: Date, hour: number, minute: number): Date {
  const jst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  const utcMidnightOfJstDay = Date.UTC(
    jst.getUTCFullYear(),
    jst.getUTCMonth(),
    jst.getUTCDate(),
  );
  return new Date(utcMidnightOfJstDay + (hour * 60 + minute) * 60_000 - 9 * 60 * 60 * 1000);
}

export async function runDailySummarySweep(): Promise<number> {
  const now = yahooNow();
  const today = jstDayKey(now);

  const settings = await prisma.notificationSetting.findMany({
    where: {
      dailySummaryAt: { not: null },
      NOT: { lastDailySummaryOn: today },
    },
  });

  let sent = 0;
  for (const setting of settings) {
    const at = parseHhMm(setting.dailySummaryAt ?? "");
    if (!at) {
      console.warn(
        `[summary] user=${setting.userId} の dailySummaryAt が "HH:MM" ではありません`,
      );
      continue;
    }
    if (now < jstTimeToday(now, at.hour, at.minute)) continue;

    // 先に「今日は送った」を立ててから送る。送信のあとに立てると、
    // 送信直後に落ちたときに翌日の走査で二重送信になる。
    // 立てるのは条件付き更新にして、同時に走った走査の片方だけを通す。
    const claimed = await prisma.notificationSetting.updateMany({
      where: { id: setting.id, NOT: { lastDailySummaryOn: today } },
      data: { lastDailySummaryOn: today },
    });
    if (claimed.count === 0) continue;

    try {
      await sendSummary(setting.userId, now);
      sent += 1;
    } catch (err) {
      console.error(`[summary] user=${setting.userId} の集計に失敗:`, err);
      // 集計に失敗したら旗を戻して、次の走査で再試行させる
      await prisma.notificationSetting.updateMany({
        where: { id: setting.id, lastDailySummaryOn: today },
        data: { lastDailySummaryOn: null },
      });
    }
  }
  return sent;
}

async function sendSummary(userId: string, now: Date): Promise<void> {
  const since = new Date(now.getTime() - 24 * 60 * 60 * 1000);

  const [active, recent, sessions, pendingApprovals, failedNotifications, lastChecked] =
    await Promise.all([
      prisma.bidReservation.findMany({
        where: { userId, status: { in: ["SCHEDULED", "MONITORING", "BIDDING"] } },
        select: { endAt: true, maxBidAmount: true },
      }),
      prisma.bidReservation.groupBy({
        by: ["status"],
        where: { userId, updatedAt: { gte: since }, status: { in: ["WON", "LOST", "FAILED", "EXPIRED", "CANCELLED", "DRY_RUN"] } },
        _count: { _all: true },
      }),
      prisma.yahooSession.findMany({
        where: { userId },
        select: { label: true, status: true, lastWatchlistSyncAt: true, lastVerifiedAt: true },
      }),
      prisma.telegramApproval.count({
        where: { status: "PENDING", reservation: { userId } },
      }),
      prisma.notification.count({
        where: { userId, createdAt: { gte: since }, deliveryError: { not: null } },
      }),
      prisma.bidReservation.aggregate({
        where: { userId },
        _max: { priceCheckedAt: true },
      }),
    ]);

  const todayCount = active.filter((r) => isSameJstDay(r.endAt, now)).length;
  const totalCap = active.reduce((sum, r) => sum + r.maxBidAmount, 0);
  const countOf = (status: string) =>
    recent.find((r) => r.status === status)?._count._all ?? 0;

  const lastPriceCheck = lastChecked._max.priceCheckedAt;
  const lines = [
    `予約中: ${active.length}件(本日終了 ${todayCount}件 / 上限額合計 ¥${totalCap.toLocaleString("ja-JP")})`,
    `直近24時間: 落札 ${countOf("WON")} / 落札ならず ${countOf("LOST")} / 失敗 ${countOf("FAILED")} / スキップ ${countOf("EXPIRED")} / 取りやめ ${countOf("CANCELLED")}`,
    // テスト実行は別行にする。上の行に混ぜると「入札した件数」に見えるし、
    // 集計対象(status の in)に入れたまま表示しないと、数えたのに
    // どこにも出ない件が生まれる。
    ...(countOf("DRY_RUN") > 0 ? [`テスト実行(入札なし): ${countOf("DRY_RUN")}件`] : []),
    `承認待ち: ${pendingApprovals}件`,
    lastPriceCheck
      ? `最終価格取得: ${formatJstTime(lastPriceCheck)}(${Math.round((now.getTime() - lastPriceCheck.getTime()) / 60_000)}分前)`
      : "最終価格取得: まだ一度も取得できていません",
    failedNotifications > 0
      ? `⚠️ 通知の送信失敗: 直近24時間で ${failedNotifications}件(片方の経路が死んでいる可能性)`
      : "通知の送信失敗: 0件",
  ];

  // 生存確認が「判定できない」を返し続けると lastVerifiedAt が進まない。
  // 失効判定は出ないので通知は静かなまま = ここが唯一の異常サインになる。
  const staleVerifyMs = 24 * 60 * 60 * 1000;
  for (const s of sessions) {
    const sync = s.lastWatchlistSyncAt
      ? `${formatJstTime(s.lastWatchlistSyncAt)} に同期`
      : "未同期";
    const verified = s.lastVerifiedAt
      ? `${formatJstTime(s.lastVerifiedAt)} に確認`
      : "未確認";
    const stale =
      s.status === "ACTIVE" &&
      (!s.lastVerifiedAt || now.getTime() - s.lastVerifiedAt.getTime() > staleVerifyMs);
    lines.push(
      `${stale ? "⚠️ " : ""}連携「${s.label}」: ${s.status} / ログイン確認 ${verified} / ウォッチリスト ${sync}`,
    );
  }
  if (sessions.length === 0) lines.push("⚠️ ヤフオク連携が1件も登録されていません");

  await notifyUser(userId, "DAILY_SUMMARY", { _lines: lines });
}
