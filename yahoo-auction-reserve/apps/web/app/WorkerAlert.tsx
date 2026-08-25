import { prisma } from "@yar/db";
import { judgeWorkerLiveness, workerLivenessMessage } from "@yar/shared/liveness";

/**
 * worker が止まっていることを全ページの先頭で知らせる。
 *
 * ⚠️ このアプリは Mac 常駐でしか動かせない(ヤフオクはデータセンター IP を
 * 403 で弾く)。外出先から画面が見えるようになると、Mac のスリープが
 * 「画面は開くのに入札だけ実行されない」という無症状の故障に化ける。
 * 一覧や予約詳細だけに出すと、その画面を開かない日は気づけないので
 * レイアウト直下に置く。
 */
export default async function WorkerAlert() {
  // 表示のためだけに全ページを落とさない。DB が読めないなら黙って何も出さず、
  // 本来のページ側のエラー表示に任せる。
  const row = await prisma.workerHeartbeat
    .findUnique({ where: { id: "singleton" }, select: { beatAt: true } })
    .catch(() => null);

  const message = workerLivenessMessage(judgeWorkerLiveness(row?.beatAt, new Date()));
  if (!message) return null;

  return (
    <div className="worker-alert" role="alert">
      <strong>入札は停止中です</strong>
      <span>{message}</span>
    </div>
  );
}
