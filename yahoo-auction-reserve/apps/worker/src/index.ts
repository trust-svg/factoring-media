// 最初に .env を読む(module スコープで環境変数を読むモジュールがあるため順序が重要)
import "./env";
import { Worker } from "bullmq";
import { connection, type ReservationJobData } from "./queues";
import { runRefreshJob } from "./jobs/refresh";
import { runMonitorJob } from "./jobs/monitor";
import { startScheduler } from "./scheduler";
import { measureYahooTimeOffset } from "./time";

async function main(): Promise<void> {
  await measureYahooTimeOffset();
  // 定期的にヤフオク時刻オフセットを更新
  setInterval(() => void measureYahooTimeOffset(), 5 * 60 * 1000);

  const refreshWorker = new Worker<ReservationJobData>("refresh", runRefreshJob, {
    connection,
    concurrency: 5,
  });
  // 入札実行はブラウザを伴うため並列度を絞る。
  // 同一ヤフオクセッションの直列化(設計 §7.4)はフェーズ2で group 機能により実装予定。
  const monitorWorker = new Worker<ReservationJobData>("monitor", runMonitorJob, {
    connection,
    concurrency: 4,
    lockDuration: 45 * 60 * 1000, // 自動延長ループ上限(30分)より長く
  });

  for (const w of [refreshWorker, monitorWorker]) {
    w.on("failed", (job, err) => {
      console.error(`[worker] job ${job?.name}:${job?.id} failed:`, err.message);
    });
  }

  const scheduler = startScheduler();
  console.log("[worker] started: refresh(x5) monitor(x4) scheduler(30s)");

  const shutdown = async () => {
    clearInterval(scheduler);
    await Promise.allSettled([refreshWorker.close(), monitorWorker.close()]);
    await connection.quit();
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

main().catch((err) => {
  console.error("[worker] fatal:", err);
  process.exit(1);
});
