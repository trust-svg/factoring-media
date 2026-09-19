import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { alreadyHighestGuard } from "./alreadyHighest";

// 数字は 2026-09-19 の実害(l1244376785)から取る。作った数字で固めると、
// 「その場で通る条件」を書いただけの検証になる。
const INCIDENT = { lastBidAmount: 22_500, currentPrice: 29_000 };

describe("alreadyHighestGuard", () => {
  it("現在価格が前回の入札額を超えていたらガードを無効化する(実害の再現)", () => {
    const g = alreadyHighestGuard(INCIDENT);
    assert.equal(g.enabled, false);
    assert.ok(g.reason.includes("29000"), `理由に現在価格が無い: ${g.reason}`);
    assert.ok(g.reason.includes("22500"), `理由に前回入札額が無い: ${g.reason}`);
  });

  it("理由は必ず書く(無効化したことが黙って起きない)", () => {
    assert.notEqual(alreadyHighestGuard(INCIDENT).reason, "");
  });

  it("現在価格が前回の入札額以下ならガードは有効のまま", () => {
    // 上限 ¥22,500 で入札して現在価格 ¥9,980 = 自分が最高額のままの姿。
    // これが実害の1回目のループの実値。
    assert.equal(
      alreadyHighestGuard({ lastBidAmount: 22_500, currentPrice: 9_980 }).enabled,
      true,
    );
  });

  it("同額では打ち消さない(先の入札者が上位なので自分が最高額でありうる)", () => {
    assert.equal(
      alreadyHighestGuard({ lastBidAmount: 22_500, currentPrice: 22_500 }).enabled,
      true,
    );
  });

  it("まだ入札していない回は打ち消さない(比較材料が無い)", () => {
    assert.equal(
      alreadyHighestGuard({ lastBidAmount: null, currentPrice: 29_000 }).enabled,
      true,
    );
  });

  it("価格が取れなかった回は打ち消さない(材料が無いのに確証を名乗らない)", () => {
    assert.equal(
      alreadyHighestGuard({ lastBidAmount: 22_500, currentPrice: null }).enabled,
      true,
    );
  });

  it("有効のままのときは理由を書かない(ログに無意味な行を出さない)", () => {
    assert.equal(alreadyHighestGuard({ lastBidAmount: null, currentPrice: null }).reason, "");
  });
});
