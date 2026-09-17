import assert from "node:assert/strict";
import test from "node:test";
import {
  judgeManualWatchlistSync,
  MANUAL_WATCHLIST_SYNC_MIN_INTERVAL_MS,
  type ManualSyncSessionState,
} from "./watchlistSyncRequest";

const now = new Date("2026-09-17T19:00:00+09:00").getTime();
const ago = (ms: number) => new Date(now - ms);
const S = (
  lastWatchlistSyncAt: Date | null,
  watchlistSyncRequestedAt: Date | null = null,
): ManualSyncSessionState => ({ lastWatchlistSyncAt, watchlistSyncRequestedAt });

test("連携が無ければ受け付けない", () => {
  assert.deepEqual(judgeManualWatchlistSync([], now), { kind: "NO_SESSION" });
});

test("最短間隔を過ぎていれば受け付ける", () => {
  const v = judgeManualWatchlistSync([S(ago(MANUAL_WATCHLIST_SYNC_MIN_INTERVAL_MS + 1))], now);
  assert.deepEqual(v, { kind: "ACCEPT" });
});

test("同期したばかりなら断り、残り秒を返す", () => {
  const v = judgeManualWatchlistSync([S(ago(60_000))], now);
  assert.deepEqual(v, { kind: "TOO_SOON", retryAfterSec: 120 });
});

test("要求が残っている間は何度押しても1回ぶん(PENDING)", () => {
  // ⚠️ ここを ACCEPT にすると、同期中に連打したぶんだけ
  //    ヤフオクへのアクセスが積み上がる
  const v = judgeManualWatchlistSync([S(ago(10 * 60_000), ago(20_000))], now);
  assert.deepEqual(v, { kind: "PENDING" });
});

test("実行中(同期時刻は古いまま・要求だけ立っている)は素通しさせない", () => {
  // 同期は数十秒〜数分かかる。その間 lastWatchlistSyncAt は進まないので、
  // 経過時間だけで測る実装だと走っている最中に何回でも通ってしまう
  const v = judgeManualWatchlistSync([S(ago(59 * 60_000), ago(5_000))], now);
  assert.equal(v.kind, "PENDING");
});

test("一度も同期できていない連携は待たせない", () => {
  assert.deepEqual(judgeManualWatchlistSync([S(null)], now), { kind: "ACCEPT" });
});

test("連携が複数あるときは一番新しい同期で測る", () => {
  // 古いほうで測ると、片方が止まっている間ずっと素通しになる
  const v = judgeManualWatchlistSync([S(ago(60 * 60_000)), S(ago(30_000))], now);
  assert.deepEqual(v, { kind: "TOO_SOON", retryAfterSec: 150 });
});

test("未来の同期時刻(時計ずれ)でも案内は最短間隔を超えない", () => {
  const v = judgeManualWatchlistSync([S(new Date(now + 60 * 60_000))], now);
  assert.equal(v.kind, "TOO_SOON");
  assert.equal(
    v.kind === "TOO_SOON" && v.retryAfterSec,
    MANUAL_WATCHLIST_SYNC_MIN_INTERVAL_MS / 1000,
  );
});
