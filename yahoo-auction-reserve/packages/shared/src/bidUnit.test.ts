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

  // 2026-08-28 の P0 で実際に踏んだ回。現在価格4,900円の商品に 4,901 を入れて
  // Stage 2 を回し、確認画面に着けずに1往復を無駄にした。
  // 「現在価格より1円でも高ければ通る」ではない。
  it("現在価格を1円上回るだけでは足りない — 2026-08-28 の実測ケース", () => {
    assert.equal(minimumBidToBeat(4_900), 5_000);
    assert.ok(4_901 < minimumBidToBeat(4_900), "4,901 は最低入札額に届かない");
  });
});

describe("minimumBidToBeat の入札0件", () => {
  it("入札0件なら現在価格ちょうどで入札できる", () => {
    // 開始価格のまま誰も入札していない商品。単位を足すと過大になる。
    assert.equal(minimumBidToBeat(1, 0), 1);
    assert.equal(minimumBidToBeat(13_500, 0), 13_500);
  });

  it("入札があれば単位を足す", () => {
    assert.equal(minimumBidToBeat(1, 10), 11);
    assert.equal(minimumBidToBeat(13_500, 2), 14_000);
  });

  it("件数が分からないときは弾かれない側(単位を足す)に倒す", () => {
    // 足りない額は弾かれて入札が成立しない。多い額は自動入札の上限が
    // 上がるだけ。分からないときは安いほうではなく、通るほうを選ぶ。
    assert.equal(minimumBidToBeat(1), 11);
    assert.equal(minimumBidToBeat(1, undefined), 11);
  });
});
