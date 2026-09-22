// monitor ジョブを入れ替えるかどうかの判断。
//
// Redis にも DB にも触らないモジュールに切り出してある。理由は2つ:
//   - ここが壊れると「入札が2回走る」か「1回も走らない」のどちらかになり、
//     どちらも本番の1回きりの瞬間にしか現れない。テストで固定したい。
//   - scheduler.ts を import すると ./queues 経由で Redis に接続しにいき、
//     テストが終わらなくなる。

export type MonitorJobState = "delayed" | "waiting" | "active";

export interface MonitorJobRef {
  id: string;
  state: MonitorJobState;
  /** 実際に消す手段。純粋な計画部(planMonitorEnqueue)からは呼ばない */
  remove?: () => Promise<void>;
}

export interface MonitorEnqueuePlan {
  add: boolean;
  removeIds: string[];
  /** add しないと決めた理由。ログに出す用 */
  skipReason?: string;
}

/**
 * 同じ予約に対する既存 monitor ジョブを見て、消すもの・入れるものを決める。
 *
 * Redis に触らない純粋関数にしてあるのは、ここが壊れると
 * 「入札が2回走る」か「1回も走らない」のどちらかになるため
 * (どちらも本番でしか気づけない)。
 */
export function planMonitorEnqueue(
  desiredJobId: string,
  existing: MonitorJobRef[],
): MonitorEnqueuePlan {
  // 実行中なら何もしない。別 jobId で足すと、同じ予約に監視が2本になり
  // 入札が2回飛びうる(取り消せない)。
  const active = existing.find((j) => j.state === "active");
  if (active) {
    return { add: false, removeIds: [], skipReason: `実行中のジョブがある(${active.id})` };
  }
  return {
    add: true,
    removeIds: existing.filter((j) => j.id !== desiredJobId).map((j) => j.id),
  };
}
