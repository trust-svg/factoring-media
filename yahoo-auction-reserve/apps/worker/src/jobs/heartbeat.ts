import { prisma } from "@yar/db";

// worker の鼓動。スケジューラの走査ごとに1行を上書きし、web 側はこの時刻から
// 生死を判定する(判定ロジックは @yar/shared の judgeWorkerLiveness)。
//
// ⚠️ **他の走査の成否に関わらず打つ。** 「全部成功したときだけ打つ」に
// すると、1つのジョブが恒常的に失敗している間ずっと「worker 停止」と表示され、
// 本当に止まった日の警告が信用されなくなる。ジョブの失敗は通知・ログの担当。

const HEARTBEAT_ID = "singleton";

export async function beat(now: Date = new Date()): Promise<void> {
  await prisma.workerHeartbeat.upsert({
    where: { id: HEARTBEAT_ID },
    create: { id: HEARTBEAT_ID, beatAt: now, startedAt: now },
    update: { beatAt: now },
  });
}
