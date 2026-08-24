import { prisma } from "@yar/db";
import {
  MONITOR_LEAD_SECONDS,
  REFRESH_INTERVAL_FAR_MS,
  REFRESH_INTERVAL_NEAR_MS,
} from "@yar/shared";
import { monitorQueue, refreshQueue } from "./queues";

// 予約の真実は DB(BidReservation)。Redis のジョブはここから常に再構築できる
// ようにし、Redis 消失・Worker 再起動から自己修復する(設計 §4, §7.3)。
//
// jobId をリソースごとに決定的にすることで二重登録を防ぐ:
// - monitor: monitor:<reservationId>:<endAt epoch> (延長で endAt が変わると別ジョブ)
// - refresh: refresh:<reservationId> (repeat ではなく都度 delayed で入れ直す)
const SCAN_INTERVAL_MS = 30_000;

export function startScheduler(): NodeJS.Timeout {
  const timer = setInterval(() => {
    scanOnce().catch((err) => console.error("[scheduler] scan failed:", err));
  }, SCAN_INTERVAL_MS);
  scanOnce().catch((err) => console.error("[scheduler] scan failed:", err));
  return timer;
}

export async function scanOnce(): Promise<void> {
  const now = Date.now();
  const reservations = await prisma.bidReservation.findMany({
    where: { status: { in: ["SCHEDULED", "MONITORING"] } },
    select: { id: true, endAt: true, status: true },
  });

  for (const r of reservations) {
    const endMs = r.endAt.getTime();
    const monitorAt = endMs - MONITOR_LEAD_SECONDS * 1000;

    // monitor: 終了90秒前に起動。過去時刻なら即時実行
    await monitorQueue.add(
      "monitor",
      { reservationId: r.id },
      {
        jobId: `monitor:${r.id}:${endMs}`,
        delay: Math.max(0, monitorAt - now),
        removeOnComplete: true,
        removeOnFail: 100,
      },
    );

    // refresh: SCHEDULED の間だけ、残り時間に応じた間隔で次回分を予約
    if (r.status === "SCHEDULED") {
      const interval =
        endMs - now > 15 * 60 * 1000
          ? REFRESH_INTERVAL_FAR_MS
          : REFRESH_INTERVAL_NEAR_MS;
      const existing = await refreshQueue.getJob(`refresh:${r.id}`);
      if (!existing) {
        await refreshQueue.add(
          "refresh",
          { reservationId: r.id },
          {
            jobId: `refresh:${r.id}`,
            delay: interval,
            removeOnComplete: true,
            removeOnFail: 100,
          },
        );
      }
    }
  }
}
