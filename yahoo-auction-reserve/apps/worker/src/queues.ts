import { Queue } from "bullmq";
import IORedis from "ioredis";

export const connection = new IORedis(
  process.env.REDIS_URL ?? "redis://localhost:6379",
  { maxRetriesPerRequest: null },
);

// refresh: 商品情報の定期更新(HTTP・軽量)
// monitor: 終了間際のブラウザウォームアップ+スナイプ実行(Playwright)
export const refreshQueue = new Queue("refresh", { connection });
export const monitorQueue = new Queue("monitor", { connection });

export interface ReservationJobData {
  reservationId: string;
}
