import { prisma } from "@yar/db";
import {
  monitorLeadSeconds,
  REFRESH_INTERVAL_FAR_MS,
  REFRESH_INTERVAL_NEAR_MS,
} from "@yar/shared";
import { monitorQueue, refreshQueue } from "./queues";
import { runReminderSweep } from "./jobs/reminder";
import { runDailySummarySweep } from "./jobs/dailySummary";
import { runWatchlistSweep } from "./jobs/watchlist";
import { runEnrichSweep } from "./jobs/enrich";
import { sweepApprovals } from "./approvalPoller";

// 予約の真実は DB(BidReservation)。Redis のジョブはここから常に再構築できる
// ようにし、Redis 消失・Worker 再起動から自己修復する(設計 §4, §7.3)。
//
// jobId をリソースごとに決定的にすることで二重登録を防ぐ:
// - monitor: monitor-<reservationId>-<endAt epoch> (延長で endAt が変わると別ジョブ)
// - refresh: refresh-<reservationId> (repeat ではなく都度 delayed で入れ直す)
//
// 区切りに ":" は使えない。BullMQ は「":" を含む jobId は 3 分割になるものだけ」
// (旧 repeatable job 互換)しか通さず、それ以外は add 時に例外を投げる。
// (旧実装は "refresh:<id>" で毎回 add に失敗し、走査ごと落ちて refresh が
//  一度も動いていなかった。2026-08-24 のスモークテストで検出)
const SCAN_INTERVAL_MS = 30_000;

// ウォッチリスト同期の間隔。ブラウザを起動するので refresh より粗く回す。
// これ自体がヤフオクのログイン維持確認を兼ねる(設計追補 2026-08-25)。
const WATCHLIST_INTERVAL_MS = 60 * 60 * 1000;

export interface SchedulerHandle {
  stop: () => void;
}

export function startScheduler(): SchedulerHandle {
  const run = (label: string, fn: () => Promise<unknown>) => {
    fn().catch((err) => console.error(`[scheduler] ${label} failed:`, err));
  };

  // 走査ごとに独立して回す。1つが失敗しても他を止めない
  // (まとめて await すると、リマインドの失敗で入札の登録まで落ちる)。
  const tick = () => {
    run("scan", scanOnce);
    run("reminder", runReminderSweep);
    run("dailySummary", runDailySummarySweep);
    run("approvalSweep", sweepApprovals);
    run("enrich", runEnrichSweep);
  };
  const timer = setInterval(tick, SCAN_INTERVAL_MS);
  tick();

  const watchlistTimer = setInterval(
    () => run("watchlist", runWatchlistSweep),
    WATCHLIST_INTERVAL_MS,
  );
  run("watchlist", runWatchlistSweep);

  return {
    stop: () => {
      clearInterval(timer);
      clearInterval(watchlistTimer);
    },
  };
}

export async function scanOnce(): Promise<void> {
  const now = Date.now();
  const reservations = await prisma.bidReservation.findMany({
    where: { status: { in: ["SCHEDULED", "MONITORING"] } },
    select: { id: true, endAt: true, status: true, snipeSecondsBefore: true },
  });

  for (const r of reservations) {
    // 1件の失敗で走査全体を止めない。止めると後続の予約に monitor ジョブが
    // 一切入らず、「エラーログは出ているのに入札だけ実行されない」状態になる。
    try {
      await enqueueFor(r, now);
    } catch (err) {
      console.error(`[scheduler] enqueue failed for ${r.id}:`, err);
    }
  }
}

interface ScannedReservation {
  id: string;
  endAt: Date;
  status: string;
  snipeSecondsBefore: number;
}

async function enqueueFor(r: ScannedReservation, now: number): Promise<void> {
  const endMs = r.endAt.getTime();
  // 起動時刻は予約ごとに違う。固定値にすると snipeSecondsBefore が大きい予約で
  // 「起きた時点で入札予定時刻を過ぎている」状態になり、黙って早く入札する。
  const monitorAt = endMs - monitorLeadSeconds(r.snipeSecondsBefore) * 1000;

  // monitor: 入札予定時刻のウォームアップ分だけ手前で起動。過去時刻なら即時実行
  await monitorQueue.add(
    "monitor",
    { reservationId: r.id },
    {
      jobId: `monitor-${r.id}-${endMs}`,
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
    const existing = await refreshQueue.getJob(`refresh-${r.id}`);
    if (!existing) {
      await refreshQueue.add(
        "refresh",
        { reservationId: r.id },
        {
          jobId: `refresh-${r.id}`,
          delay: interval,
          removeOnComplete: true,
          removeOnFail: 100,
        },
      );
    }
  }
}
