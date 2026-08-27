import assert from "node:assert/strict";
import test from "node:test";
import { isSeenInLatestSync } from "./watchFreshness";

const sync = new Date("2026-08-28T00:00:00+09:00");
const F = (lastSeen: Date, lastSync: Date | null = sync) =>
  isSeenInLatestSync({ lastSeenAt: lastSeen, sessionLastSyncAt: lastSync });

test("同じ同期で見えた商品は出す(同時刻は「見えた」側)", () => {
  // ⚠️ 同期は全商品と連携の同期時刻を **同じ値** で刻む(jobs/watchlist.ts)。
  // ここを > にすると、正しく取れた商品が毎回1件残らず消える
  assert.equal(F(sync), true);
});

test("前回の同期でしか見ていない商品は出さない — 2026-08-28 に61件居座った", () => {
  const oneHourAgo = new Date(sync.getTime() - 60 * 60 * 1000);
  assert.equal(F(oneHourAgo), false);
});

test("1ミリ秒でも古ければ出さない", () => {
  assert.equal(F(new Date(sync.getTime() - 1)), false);
});

test("同期時刻より新しい商品も出す(順序の取り違えで隠さない)", () => {
  assert.equal(F(new Date(sync.getTime() + 1)), true);
});

test("一度も同期が成功していない連携の商品は隠さない(安全側に非対称)", () => {
  // 隠すほうに倒すと、一覧が空になったうえに理由も出ない。
  // 出すほうの害は「ウォッチしていない商品が並ぶ」で、見れば気づける
  assert.equal(F(new Date("2020-01-01T00:00:00Z"), null), true);
});
