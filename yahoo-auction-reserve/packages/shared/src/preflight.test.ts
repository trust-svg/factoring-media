import assert from "node:assert/strict";
import test from "node:test";
import {
  PREFLIGHT_BROWSER_CUTOFF_MS,
  PREFLIGHT_LEAD_MS,
  PREFLIGHT_TRUST_MS,
  planPreflight,
  preflightScanHorizonMs,
} from "./preflight";
import { monitorLeadSeconds, SNIPE_SECONDS_MAX } from "./constants";
import type { SessionStatusKey } from "./labels";

const endAt = new Date("2026-09-22T22:00:00+09:00");
const SNIPE = 30;
/** monitor が起きる時刻。事前確認の締切はここであって endAt ではない */
const monitorStart = endAt.getTime() - monitorLeadSeconds(SNIPE) * 1000;

const P = (
  now: number,
  status: SessionStatusKey = "ACTIVE",
  lastVerifiedAt: Date | null = null,
  snipeSecondsBefore = SNIPE,
) =>
  planPreflight({
    now: new Date(now),
    endAt,
    snipeSecondsBefore,
    sessionStatus: status,
    sessionLastVerifiedAt: lastVerifiedAt,
  }).kind;

test("窓に入る前は何もしない", () => {
  assert.equal(P(monitorStart - PREFLIGHT_LEAD_MS - 1), "wait");
});

test("窓の開始ちょうどは窓の中(同時刻は「入った」側)", () => {
  assert.equal(P(monitorStart - PREFLIGHT_LEAD_MS), "verify");
});

test("窓に入ったら開いて確かめる", () => {
  assert.equal(P(monitorStart - 30 * 60 * 1000), "verify");
});

test("連携が失効していたら、開かずに即通知する", () => {
  // ⚠️ ここが案 C の主目的。失効した連携を指す予約は、定期の生存確認が
  //    ACTIVE だけを走査するので **永久に検査対象から外れている**
  assert.equal(P(monitorStart - 30 * 60 * 1000, "EXPIRED"), "notify-dead");
});

test("解除済みの連携を指す予約も即通知する", () => {
  assert.equal(P(monitorStart - 30 * 60 * 1000, "REVOKED"), "notify-dead");
});

test("不正な連携を指す予約も即通知する", () => {
  assert.equal(P(monitorStart - 30 * 60 * 1000, "INVALID"), "notify-dead");
});

test("連携が死んでいれば、monitor 起動の直前でも通知する", () => {
  // 通知にブラウザは要らないので、ブラウザ確認の打ち切りより優先する。
  // 間に合わなくても「この予約は失敗する」と分かるほうがよい
  assert.equal(P(monitorStart - 1000, "EXPIRED"), "notify-dead");
});

test("monitor の起動が近いときはブラウザを開かない", () => {
  // ⚠️ 監視ジョブもヘッドレスブラウザを起動する。ここで開くと
  //    入札の直前に Mac の資源を取り合う
  assert.equal(P(monitorStart - PREFLIGHT_BROWSER_CUTOFF_MS), "too-late");
  assert.equal(P(monitorStart - PREFLIGHT_BROWSER_CUTOFF_MS + 1), "too-late");
});

test("打ち切りの1ミリ秒前なら、まだ開いて確かめる", () => {
  assert.equal(P(monitorStart - PREFLIGHT_BROWSER_CUTOFF_MS - 1), "verify");
});

test("直近に確認できている連携はブラウザを開かない", () => {
  const now = monitorStart - 30 * 60 * 1000;
  const justChecked = new Date(now - PREFLIGHT_TRUST_MS + 1);
  assert.equal(P(now, "ACTIVE", justChecked), "trust");
});

test("確認が古ければ開いて確かめ直す", () => {
  const now = monitorStart - 30 * 60 * 1000;
  const stale = new Date(now - PREFLIGHT_TRUST_MS);
  assert.equal(P(now, "ACTIVE", stale), "verify");
});

test("締切は endAt ではなく monitor の起動時刻を基準にする", () => {
  // ⚠️ snipeSecondsBefore は最大600秒まで伸ばせる。endAt を基準にすると、
  //    実行秒数の長い予約では **監視が始まってから** 事前確認が動くことになり、
  //    再連携する時間も無ければブラウザも取り合う
  const longSnipe = 600;
  const longMonitorStart = endAt.getTime() - monitorLeadSeconds(longSnipe) * 1000;

  // endAt 基準なら「まだ60分前ではない」時刻。monitor 基準なら窓の中
  const now = longMonitorStart - PREFLIGHT_LEAD_MS + 1000;
  assert.equal(P(now, "ACTIVE", null, longSnipe), "verify");

  // 同じ時刻でも、実行秒数が短い予約はまだ窓の外
  assert.equal(P(now, "ACTIVE", null, SNIPE), "wait");
});

test("死んだ連携でも、窓に入る前は通知しない(終了の何日も前に騒がない)", () => {
  assert.equal(P(monitorStart - PREFLIGHT_LEAD_MS - 1, "EXPIRED"), "wait");
});

test("走査の上限は、実行秒数が最大の予約が窓に入る時刻を必ず含む", () => {
  // ⚠️ snipeSecondsBefore は予約ごとに違うので、SQL では monitor の起動時刻を
  //    計算できない。上限を狭く取ると、実行秒数の長い予約だけが **一度も
  //    走査に載らないまま** 入札時刻を迎える(しかも静かに)。
  const horizon = preflightScanHorizonMs(SNIPE_SECONDS_MAX);
  const longMonitorStart =
    endAt.getTime() - monitorLeadSeconds(SNIPE_SECONDS_MAX) * 1000;
  const windowOpensAt = longMonitorStart - PREFLIGHT_LEAD_MS;

  // 窓が開いた瞬間、その予約の endAt は「いま + horizon」の内側にいる
  assert.ok(endAt.getTime() - windowOpensAt <= horizon);
});

test("走査の上限は、実行秒数が既定の予約でも窓の開始を含む", () => {
  const horizon = preflightScanHorizonMs(SNIPE_SECONDS_MAX);
  const windowOpensAt = monitorStart - PREFLIGHT_LEAD_MS;
  assert.ok(endAt.getTime() - windowOpensAt <= horizon);
});
