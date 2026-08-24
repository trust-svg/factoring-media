import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { yahooBidUnit, minimumBidToBeat } from "./bidUnit";

describe("yahooBidUnit", () => {
  it("価格帯ごとに単位が変わる", () => {
    assert.equal(yahooBidUnit(0), 10);
    assert.equal(yahooBidUnit(999), 10);
    assert.equal(yahooBidUnit(1_000), 100);
    assert.equal(yahooBidUnit(4_999), 100);
    assert.equal(yahooBidUnit(5_000), 250);
    assert.equal(yahooBidUnit(9_999), 250);
    assert.equal(yahooBidUnit(10_000), 500);
    assert.equal(yahooBidUnit(49_999), 500);
    assert.equal(yahooBidUnit(50_000), 1_000);
    assert.equal(yahooBidUnit(1_000_000), 1_000);
  });

  it("境界は「その価格ちょうど」で上の段に入る(下の段に留めると弾かれる)", () => {
    assert.notEqual(yahooBidUnit(4_999), yahooBidUnit(5_000));
    assert.notEqual(yahooBidUnit(9_999), yahooBidUnit(10_000));
  });

  it("壊れた入力でも例外を投げず、最小の単位を返す", () => {
    assert.equal(yahooBidUnit(Number.NaN), 10);
    assert.equal(yahooBidUnit(-1), 10);
  });
});

describe("minimumBidToBeat", () => {
  it("必ず現在価格より大きい", () => {
    for (const p of [0, 999, 1_000, 4_999, 5_000, 9_999, 10_000, 49_999, 50_000, 987_654]) {
      assert.ok(minimumBidToBeat(p) > p, `${p} を上回っていない`);
    }
  });

  it("単位ぶんだけ足す", () => {
    assert.equal(minimumBidToBeat(1_400), 1_500);
    assert.equal(minimumBidToBeat(6_000), 6_250);
  });
});
