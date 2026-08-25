import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import {
  WORKER_STALE_MS,
  judgeWorkerLiveness,
  workerLivenessMessage,
} from "./liveness";

const now = new Date("2026-08-25T12:00:00+09:00");
const ago = (ms: number) => new Date(now.getTime() - ms);

describe("judgeWorkerLiveness", () => {
  it("鼓動が無ければ NEVER(worker 未起動)", () => {
    assert.equal(judgeWorkerLiveness(null, now).state, "NEVER");
    assert.equal(judgeWorkerLiveness(undefined, now).state, "NEVER");
  });

  it("直近の鼓動なら OK", () => {
    assert.equal(judgeWorkerLiveness(ago(30_000), now).state, "OK");
  });

  it("しきい値ちょうどはまだ OK(境界で点滅させない)", () => {
    assert.equal(judgeWorkerLiveness(ago(WORKER_STALE_MS), now).state, "OK");
  });

  it("しきい値を超えたら STALE", () => {
    const r = judgeWorkerLiveness(ago(WORKER_STALE_MS + 1_000), now);
    assert.equal(r.state, "STALE");
    assert.ok((r.silentForMs ?? 0) > WORKER_STALE_MS);
  });

  it("何時間も途絶えていれば当然 STALE", () => {
    assert.equal(judgeWorkerLiveness(ago(6 * 60 * 60 * 1000), now).state, "STALE");
  });

  it("鼓動が未来でも警告しない(時計ずれは生存の証拠)", () => {
    const future = new Date(now.getTime() + 60_000);
    const r = judgeWorkerLiveness(future, now);
    assert.equal(r.state, "OK");
    assert.equal(r.silentForMs, 0);
  });
});

describe("workerLivenessMessage", () => {
  it("OK のときは何も出さない", () => {
    assert.equal(workerLivenessMessage({ state: "OK", silentForMs: 1_000 }), null);
  });

  it("STALE は経過分数を含む", () => {
    const msg = workerLivenessMessage({ state: "STALE", silentForMs: 12 * 60_000 });
    assert.ok(msg);
    assert.match(msg, /12 分/);
  });

  it("NEVER は未起動と分かる文言にする", () => {
    const msg = workerLivenessMessage({ state: "NEVER", silentForMs: null });
    assert.ok(msg);
    assert.match(msg, /起動/);
  });
});
