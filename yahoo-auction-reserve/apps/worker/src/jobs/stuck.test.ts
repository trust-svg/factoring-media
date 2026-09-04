import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { STUCK_GRACE_MS, needsResultCheck, selectStuck, type StuckCandidate } from "./stuck";

const NOW = new Date("2026-09-04T05:00:00+09:00").getTime();

function row(over: Partial<StuckCandidate> = {}): StuckCandidate {
  return {
    id: "r1",
    status: "BIDDING",
    endAt: new Date(NOW - STUCK_GRACE_MS - 1000),
    hasSuccessfulBid: true,
    ...over,
  };
}

describe("取り残された予約の選別", () => {
  it("終了から猶予を過ぎ、監視ジョブも残っていないものを拾う", () => {
    assert.deepEqual(
      selectStuck([row()], new Set(), NOW).map((r) => r.id),
      ["r1"],
    );
  });

  it("監視ジョブが残っているものは拾わない", () => {
    // ⚠️ ここが効かないと、自動延長で終了時刻をまたいで走っている監視を
    // 横から終わらせてしまう(延長ループは終了時刻を過ぎても正常に走る)。
    assert.deepEqual(selectStuck([row()], new Set(["r1"]), NOW), []);
  });

  it("猶予の内側なら拾わない", () => {
    const fresh = row({ endAt: new Date(NOW - STUCK_GRACE_MS + 1000) });
    assert.deepEqual(selectStuck([fresh], new Set(), NOW), []);
  });

  it("ちょうど猶予に達したら拾う(境界)", () => {
    const edge = row({ endAt: new Date(NOW - STUCK_GRACE_MS) });
    assert.equal(selectStuck([edge], new Set(), NOW).length, 1);
  });
});

describe("結果を見に行くかの判定", () => {
  it("BIDDING は成功記録が無くても見に行く", () => {
    // placeBid が通った直後・BidAttempt を書く前に落ちる窓がある。
    // 記録だけで判断すると、落札しているのに「入札できませんでした」を送る。
    assert.equal(needsResultCheck({ status: "BIDDING", hasSuccessfulBid: false }), true);
  });

  it("MONITORING で成功記録が無ければ見に行かない(入札を送る前に落ちている)", () => {
    assert.equal(needsResultCheck({ status: "MONITORING", hasSuccessfulBid: false }), false);
  });

  it("MONITORING でも成功記録があれば見に行く(延長ループの途中で落ちた)", () => {
    assert.equal(needsResultCheck({ status: "MONITORING", hasSuccessfulBid: true }), true);
  });
});
