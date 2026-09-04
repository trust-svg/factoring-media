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
import { runNewSessionVerifySweep, runVerifySessionSweep } from "./jobs/verifySession";
import { beat } from "./jobs/heartbeat";
import { sweepApprovals } from "./approvalPoller";
import { runStuckSweep } from "./jobs/stuck";
import { planMonitorEnqueue, type MonitorJobRef, type MonitorJobState } from "./monitorPlan";

// 予約の真実は DB(BidReservation)。Redis のジョブはここから常に再構築できる
// ようにし、Redis 消失・Worker 再起動から自己修復する(設計 §4, §7.3)。
//
// jobId をリソースごとに決定的にすることで二重登録を防ぐ:
// - monitor: monitor-<reservationId>-<起動予定時刻 epoch>
// - refresh: refresh-<reservationId> (repeat ではなく都度 delayed で入れ直す)
//
// ⚠️ monitor の jobId は **起動予定時刻** で決める(endAt ではない)。
// BullMQ は既存 jobId への add を **例外も出さず黙って捨てる**。delay も
// 更新されないので、jobId に入っていない値を後から変えると、ジョブは古い
// 時刻のまま残る。endAt だけを鍵にしていた 2026-08-28 は、予約作成後に
// snipeSecondsBefore を 30→360 に変えたのに monitor は 30 秒用の時刻で
// 起き、入札が予定より 273 秒遅れた(残り6分のはずが残り1分)。
//
// 鍵を変えるだけでは足りない。古い jobId のジョブは delayed に残り続けるので
// **同じ予約の別 jobId は消してから入れ直す**。消さないと、延長された予約で
// 監視が2本走る(旧 endAt 用と新 endAt 用)。
// ただし実行中(active)のジョブには触らない。消せないうえ、消せたとしても
// 入札の最中に監視を落とすことになる。
//
// 区切りに ":" は使えない。BullMQ は「":" を含む jobId は 3 分割になるものだけ」
// (旧 repeatable job 互換)しか通さず、それ以外は add 時に例外を投げる。
// (旧実装は "refresh:<id>" で毎回 add に失敗し、走査ごと落ちて refresh が
//  一度も動いていなかった。2026-08-24 のスモークテストで検出)
const SCAN_INTERVAL_MS = 30_000;

// ウォッチリスト同期の間隔。ブラウザを起動するので refresh より粗く回す。
// これ自体がヤフオクのログイン維持確認を兼ねる(設計追補 2026-08-25)。
const WATCHLIST_INTERVAL_MS = 60 * 60 * 1000;

// 連携 Cookie の生存確認。走査自体は 15 分ごとに回すが、実際に開くのは
// 前回の確認から 6 時間経った連携だけ(判定は jobs/verifySession.ts)。
const VERIFY_SESSION_INTERVAL_MS = 15 * 60 * 1000;

// 走行中のまま取り残された予約の掃除。監視ジョブの一覧を Redis から取り直すので
// 30秒の走査には載せず、独立して粗く回す(対象の猶予が15分なので十分)。
const STUCK_INTERVAL_MS = 5 * 60 * 1000;

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
    // 鼓動は最初に打つ。他の走査の後ろに置くと、同期的に例外を投げるジョブが
    // 1つ増えた日に鼓動ごと止まり、「worker 停止」の誤報になる。
    run("heartbeat", () => beat());
    run("scan", scanOnce);
    run("reminder", runReminderSweep);
    run("dailySummary", runDailySummarySweep);
    run("approvalSweep", sweepApprovals);
    run("enrich", runEnrichSweep);
    // 登録直後の連携だけ、定期走査(6時間)を待たずにここで確認する。
    // 対象は「まだ一度も試していない」ものだけなので、通常は空振り1クエリ。
    run("verifyNewSession", runNewSessionVerifySweep);
  };
  const timer = setInterval(tick, SCAN_INTERVAL_MS);
  tick();

  const watchlistTimer = setInterval(
    () => run("watchlist", runWatchlistSweep),
    WATCHLIST_INTERVAL_MS,
  );
  run("watchlist", runWatchlistSweep);

  const verifyTimer = setInterval(
    () => run("verifySession", runVerifySessionSweep),
    VERIFY_SESSION_INTERVAL_MS,
  );
  run("verifySession", runVerifySessionSweep);

  const stuckSweep = async () => {
    const live = await collectMonitorJobs();
    return runStuckSweep(new Set(live.keys()));
  };
  const stuckTimer = setInterval(() => run("stuck", stuckSweep), STUCK_INTERVAL_MS);
  run("stuck", stuckSweep);

  return {
    stop: () => {
      clearInterval(timer);
      clearInterval(watchlistTimer);
      clearInterval(verifyTimer);
      clearInterval(stuckTimer);
    },
  };
}

export async function scanOnce(): Promise<void> {
  const now = Date.now();
  const reservations = await prisma.bidReservation.findMany({
    where: { status: { in: ["SCHEDULED", "MONITORING"] } },
    select: { id: true, endAt: true, status: true, snipeSecondsBefore: true },
  });

  // 既存の monitor ジョブは走査ごとに1回だけ読む(予約ごとに読むと
  // 予約数ぶん Redis を往復する)。
  const existingMonitors = await collectMonitorJobs();

  for (const r of reservations) {
    // 1件の失敗で走査全体を止めない。止めると後続の予約に monitor ジョブが
    // 一切入らず、「エラーログは出ているのに入札だけ実行されない」状態になる。
    try {
      await enqueueFor(r, now, existingMonitors.get(r.id) ?? []);
    } catch (err) {
      console.error(`[scheduler] enqueue failed for ${r.id}:`, err);
    }
  }
}

async function collectMonitorJobs(): Promise<Map<string, MonitorJobRef[]>> {
  const groups = new Map<string, MonitorJobRef[]>();
  const sources: Array<[MonitorJobState, Awaited<ReturnType<typeof monitorQueue.getDelayed>>]> = [
    ["delayed", await monitorQueue.getDelayed()],
    ["waiting", await monitorQueue.getWaiting()],
    ["active", await monitorQueue.getActive()],
  ];
  for (const [state, jobs] of sources) {
    for (const job of jobs) {
      const reservationId = (job.data as { reservationId?: string } | undefined)?.reservationId;
      if (!reservationId || !job.id) continue;
      const list = groups.get(reservationId) ?? [];
      list.push({ id: job.id, state, remove: () => job.remove() });
      groups.set(reservationId, list);
    }
  }
  return groups;
}

interface ScannedReservation {
  id: string;
  endAt: Date;
  status: string;
  snipeSecondsBefore: number;
}

async function enqueueFor(
  r: ScannedReservation,
  now: number,
  existingMonitors: MonitorJobRef[],
): Promise<void> {
  const endMs = r.endAt.getTime();
  // 起動時刻は予約ごとに違う。固定値にすると snipeSecondsBefore が大きい予約で
  // 「起きた時点で入札予定時刻を過ぎている」状態になり、黙って早く入札する。
  const monitorAt = endMs - monitorLeadSeconds(r.snipeSecondsBefore) * 1000;
  const jobId = `monitor-${r.id}-${monitorAt}`;

  const plan = planMonitorEnqueue(jobId, existingMonitors);
  for (const staleId of plan.removeIds) {
    const stale = existingMonitors.find((j) => j.id === staleId);
    try {
      await stale?.remove?.();
      console.log(`[scheduler] ${r.id} 古い monitor を削除: ${staleId} → ${jobId}`);
    } catch (err) {
      // 読んだ直後に active になった等。消せなかったものを残したまま
      // 新しいのを足すと監視が2本になるので、今回は入れずに次の走査に譲る。
      console.warn(`[scheduler] ${r.id} 古い monitor(${staleId}) を消せず、追加を見送り:`, err);
      return;
    }
  }
  if (!plan.add) {
    return;
  }

  // monitor: 入札予定時刻のウォームアップ分だけ手前で起動。過去時刻なら即時実行
  await monitorQueue.add(
    "monitor",
    { reservationId: r.id },
    {
      jobId,
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
