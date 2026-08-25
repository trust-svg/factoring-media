// worker(常駐プロセス)の死活判定。
//
// このアプリは Mac 常駐でしか動かせない(ヤフオクはデータセンター IP を 403 で
// 弾くため。設計 §4)。つまり **Mac がスリープ・再起動すれば入札は止まる**。
// 外出先から画面が見えるようになると、この故障が「画面は正常に開くのに予約が
// 実行されない」という一番気づけない形になる。そこで worker 側で鼓動を打ち、
// web 側は最後の鼓動からの経過で止まっているかを表示する。
//
// ⚠️ 鼓動は「ジョブが成功したこと」ではなく **走査が回っていること** を表す。
// ジョブ成功を鼓動にすると、予約が1件も無い日と worker が死んでいる日が
// 区別できなくなる(対象0件でも鼓動は打たれるのが正しい)。

/** スケジューラの走査間隔。この間隔で鼓動が更新される */
export const WORKER_HEARTBEAT_INTERVAL_MS = 30_000;

/**
 * これを超えて鼓動が無ければ停止とみなす。
 * 走査間隔の 6 回分。再起動・DB の一時的な詰まりで警告を出さない程度に緩く、
 * 「入札に間に合わない」と言える程度には短く取る。
 */
export const WORKER_STALE_MS = 3 * 60 * 1000;

export type WorkerLivenessState =
  | "OK" // 直近に鼓動があった
  | "STALE" // 鼓動が途絶えている(スリープ・停止・クラッシュ)
  | "NEVER"; // 一度も鼓動が無い(worker を起動していない)

export interface WorkerLiveness {
  state: WorkerLivenessState;
  /** 最後の鼓動からの経過ミリ秒。NEVER のときは null */
  silentForMs: number | null;
}

/**
 * 最後の鼓動時刻から worker の生死を判定する。
 *
 * ⚠️ ここは「分からないなら警告する」側に倒す。連携 Cookie の失効判定
 * (sessionVerdict.ts)が逆に「分からないなら何もしない」なのは、あちらの
 * 誤判定が再連携を強いる破壊的操作になるから。こちらは表示が出るだけなので、
 * 見落とし(止まっているのに OK と出る)の方が高くつく。
 */
export function judgeWorkerLiveness(
  lastBeatAt: Date | null | undefined,
  now: Date,
): WorkerLiveness {
  if (!lastBeatAt) return { state: "NEVER", silentForMs: null };

  const silentForMs = now.getTime() - lastBeatAt.getTime();

  // 鼓動が未来にある = ホストとDBの時計がずれているだけ。生きている証拠なので
  // 警告しない(負の経過時間で比較すると常に OK 側になるが、意図を明示しておく)。
  if (silentForMs < 0) return { state: "OK", silentForMs: 0 };

  return {
    state: silentForMs > WORKER_STALE_MS ? "STALE" : "OK",
    silentForMs,
  };
}

/** 画面に出す一文。null なら何も出さない */
export function workerLivenessMessage(liveness: WorkerLiveness): string | null {
  switch (liveness.state) {
    case "NEVER":
      return "worker がまだ一度も起動していません。予約しても入札は実行されません";
    case "STALE": {
      const minutes = Math.floor((liveness.silentForMs ?? 0) / 60_000);
      return (
        `worker が ${minutes} 分以上応答していません。` +
        "Mac がスリープ・停止している可能性があります。予約は実行されません"
      );
    }
    default:
      return null;
  }
}
