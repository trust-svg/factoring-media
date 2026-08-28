import { test } from "node:test";
import assert from "node:assert/strict";
import { planMonitorEnqueue, type MonitorJobRef } from "./monitorPlan";

// monitor ジョブの入れ替え判断。ここが壊れると入札が2回走るか1回も走らない。
// どちらも本番の1回きりの瞬間にしか現れないので、判断だけ純粋関数にして
// ここで固定する。

const DESIRED = "monitor-r1-1000";
const job = (id: string, state: MonitorJobRef["state"] = "delayed"): MonitorJobRef => ({ id, state });

test("既存が無ければそのまま入れる", () => {
  assert.deepEqual(planMonitorEnqueue(DESIRED, []), { add: true, removeIds: [] });
});

test("同じ jobId が既にあるなら消さずに入れる(BullMQ 側が無視する)", () => {
  assert.deepEqual(planMonitorEnqueue(DESIRED, [job(DESIRED)]), { add: true, removeIds: [] });
});

test("起動時刻が変わったら古いジョブを消してから入れる", () => {
  // 2026-08-28 の事故そのもの: snipeSecondsBefore を 30→360 に変えたのに
  // 古い monitor(30秒用の時刻)が delayed に残り、そちらで起きた。
  const plan = planMonitorEnqueue(DESIRED, [job("monitor-r1-700")]);
  assert.deepEqual(plan, { add: true, removeIds: ["monitor-r1-700"] });
});

test("延長で古いジョブが複数残っていても全部消す", () => {
  const plan = planMonitorEnqueue(DESIRED, [job("monitor-r1-700"), job("monitor-r1-800", "waiting")]);
  assert.deepEqual(plan.removeIds, ["monitor-r1-700", "monitor-r1-800"]);
  assert.equal(plan.add, true);
});

test("実行中のジョブがあるなら、消しも足しもしない", () => {
  // 入札の最中。別 jobId で足すと同じ予約に監視が2本になり、
  // 取り消せない入札が2回飛びうる。
  const plan = planMonitorEnqueue(DESIRED, [job("monitor-r1-700", "active")]);
  assert.equal(plan.add, false);
  assert.deepEqual(plan.removeIds, []);
  assert.match(plan.skipReason ?? "", /monitor-r1-700/);
});

test("実行中が混ざっていれば、他に古いジョブがあっても触らない", () => {
  const plan = planMonitorEnqueue(DESIRED, [job("monitor-r1-700"), job("monitor-r1-900", "active")]);
  assert.equal(plan.add, false);
  assert.deepEqual(plan.removeIds, []);
});
