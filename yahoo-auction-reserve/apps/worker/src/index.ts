// 最初に .env を読む(module スコープで環境変数を読むモジュールがあるため順序が重要)
import "./env";
import { Worker } from "bullmq";
import { connection, type ReservationJobData } from "./queues";
import { runRefreshJob } from "./jobs/refresh";
import { runMonitorJob } from "./jobs/monitor";
import { startScheduler } from "./scheduler";
import { measureYahooTimeOffset } from "./time";
import { startApprovalPoller } from "./approvalPoller";
import { telegramEnabled } from "./telegram";

async function main(): Promise<void> {
  await measureYahooTimeOffset();
  // 定期的にヤフオク時刻オフセットを更新
  setInterval(() => void measureYahooTimeOffset(), 5 * 60 * 1000);

  const refreshWorker = new Worker<ReservationJobData>("refresh", runRefreshJob, {
    connection,
    concurrency: 5,
  });
  // 入札実行はブラウザを伴うため並列度を絞る。
  // 同一ヤフオクセッションからの入札送信は sessionLock.ts で直列化する
  // (設計 §7.4)。⚠️ そのロックはプロセス内メモリなので、**worker を
  // 複数立てると直列化は効かない**。Telegram の getUpdates も 1 プロセス
  // 排他なので、worker は1つで運用すること。
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
  // 増額承認ボタンの受け口。getUpdates は 1 Bot 1 消費者なので、
  // worker を複数立てるとここが 409 になる(ログに警告が出る)。
  const approvalPoller = startApprovalPoller();
  console.log(
    "[worker] started: refresh(x5) monitor(x4) scheduler(30s) watchlist(60m) " +
      `telegram=${telegramEnabled() ? "on" : "off"}`,
  );

  const shutdown = async () => {
    scheduler.stop();
    approvalPoller.stop();
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
