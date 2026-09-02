import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { splitReservedStatuses } from "../lib/reservedStatus";

// ウォッチリスト画面は「予約が1件でもあれば予約済み」と読んでいて、
// キャンセルした商品の行から「予約する」も「一覧から消す」も消えていた
// (2026-09-02 報告)。API 側は最初から再登録を許していたので、
// **画面だけが独自の判断を持っていた** のが原因。
// 同じ判断を2箇所に書かないよう、判定は @yar/shared/labels に1つだけ置く。

test("キャンセルした予約は行を塞がない(もう一度予約できる)", () => {
  const { live, past } = splitReservedStatuses([{ auctionId: "k1", status: "CANCELLED" }]);
  assert.equal(live.has("k1"), false, "キャンセル済みなのに予約済み扱いになっている");
  assert.equal(past.get("k1"), "CANCELLED", "前回の結果が消えている");
});

test("動いている予約は予約済みとして行を塞ぐ(二重予約を防ぐ)", () => {
  const { live, past } = splitReservedStatuses([
    { auctionId: "k1", status: "SCHEDULED" },
    { auctionId: "k2", status: "MONITORING" },
    { auctionId: "k3", status: "BIDDING" },
    { auctionId: "k4", status: "WON" },
  ]);
  assert.deepEqual([...live.keys()].sort(), ["k1", "k2", "k3", "k4"]);
  assert.equal(past.size, 0);
});

test("失敗・落札ならず・スキップ・テスト実行も予約し直せる", () => {
  const rows = ["FAILED", "LOST", "EXPIRED", "DRY_RUN"].map((status, i) => ({
    auctionId: `k${i}`,
    status,
  }));
  const { live, past } = splitReservedStatuses(rows);
  assert.equal(live.size, 0);
  assert.equal(past.size, 4);
});

const WEB = join(__dirname, "..");
const API = readFileSync(join(WEB, "app/api/v1/reservations/route.ts"), "utf8");

test("予約APIも同じ判定関数を使う(終了ステータスの一覧を2箇所に書かない)", () => {
  assert.match(API, /isRebookableReservation/);
  // 旧実装の手書き一覧が復活していないこと
  assert.doesNotMatch(API, /const FINISHED = \[/);
});
