import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { judgeMarket, judgeSeller, totalWithShipping } from "./judgement";

const NO_TH = { sellerRatingFloor: null, sellerRatingMinCount: null };

describe("judgeSeller", () => {
  it("しきい値未設定なら何も言わない", () => {
    const j = judgeSeller({ sellerRating: 10, sellerRatingCount: 1 }, NO_TH);
    assert.equal(j.level, "ok");
  });

  it("割合が下限を下回れば warn", () => {
    const j = judgeSeller(
      { sellerRating: 92, sellerRatingCount: 500 },
      { sellerRatingFloor: 95, sellerRatingMinCount: null },
    );
    assert.equal(j.level, "warn");
    assert.match(j.reasons[0], /92%/);
  });

  it("下限ちょうどは通す", () => {
    const j = judgeSeller(
      { sellerRating: 95, sellerRatingCount: 500 },
      { sellerRatingFloor: 95, sellerRatingMinCount: null },
    );
    assert.equal(j.level, "ok");
  });

  it("評価が取れていない場合は ok に丸めず unknown", () => {
    // ここを ok にすると、パーサが壊れた日から全商品が足切りを素通りする
    const j = judgeSeller(
      { sellerRating: null, sellerRatingCount: null },
      { sellerRatingFloor: 95, sellerRatingMinCount: null },
    );
    assert.equal(j.level, "unknown");
  });

  it("母数不足も warn(100%でも2件は判断材料にならない)", () => {
    const j = judgeSeller(
      { sellerRating: 100, sellerRatingCount: 2 },
      { sellerRatingFloor: 95, sellerRatingMinCount: 10 },
    );
    assert.equal(j.level, "warn");
    assert.match(j.reasons[0], /2件/);
  });

  it("片方が取れていなくても、もう片方が下限割れなら warn を優先する", () => {
    const j = judgeSeller(
      { sellerRating: 50, sellerRatingCount: null },
      { sellerRatingFloor: 95, sellerRatingMinCount: 10 },
    );
    assert.equal(j.level, "warn");
  });
});

describe("judgeMarket", () => {
  it("相場が無ければ unknown", () => {
    assert.equal(judgeMarket(10_000, null, null).level, "unknown");
  });

  it("母数が少なければ判定しない", () => {
    assert.equal(judgeMarket(10_000, 1_000, 2).level, "unknown");
  });

  it("相場の1.2倍を超えたら warn", () => {
    const j = judgeMarket(12_001, 10_000, 20);
    assert.equal(j.level, "warn");
    assert.match(j.reasons[0], /20%/);
  });

  it("1.2倍ちょうどは通す", () => {
    assert.equal(judgeMarket(12_000, 10_000, 20).level, "ok");
  });
});

describe("totalWithShipping", () => {
  it("送料が分かっていれば合算する", () => {
    assert.deepEqual(totalWithShipping(10_000, 800), {
      total: 10_800,
      shippingKnown: true,
    });
  });

  it("送料無料(0)は合算できる", () => {
    assert.deepEqual(totalWithShipping(10_000, 0), {
      total: 10_000,
      shippingKnown: true,
    });
  });

  it("送料不明は 0 として足さず null を返す", () => {
    // 足すと「総額」の顔をした商品代だけの数字が出る
    assert.deepEqual(totalWithShipping(10_000, null), {
      total: null,
      shippingKnown: false,
    });
  });
});
