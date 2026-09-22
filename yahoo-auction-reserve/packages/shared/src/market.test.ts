import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  buildMarketQuery,
  closedSearchUrl,
  median,
  parseClosedPrices,
} from "./market";

describe("median", () => {
  it("奇数個は中央の値", () => {
    assert.equal(median([300, 100, 200]), 200);
  });

  it("偶数個は中央2つの平均(切り捨て)", () => {
    assert.equal(median([100, 200, 300, 401]), 250);
  });

  it("空配列は null(0 ではない)", () => {
    // 0 を返すと「相場0円」として上限額との比較が必ず警告側に倒れる
    assert.equal(median([]), null);
  });

  it("極端な外れ値に引きずられない", () => {
    // 平均なら 20,180 になるが、中央値は 200 のまま
    assert.equal(median([100, 200, 300, 100_000, 100]), 200);
  });

  it("引数の配列を破壊しない", () => {
    const src = [300, 100, 200];
    median(src);
    assert.deepEqual(src, [300, 100, 200]);
  });
});

describe("buildMarketQuery", () => {
  it("記号と状態語を落とす", () => {
    assert.equal(
      buildMarketQuery("【美品】Nikon F3 ボディ (送料無料)"),
      "Nikon F3 ボディ",
    );
  });

  it("語数を上限で打ち切る", () => {
    assert.equal(buildMarketQuery("a b c d e f g h", 3), "a b c");
  });

  it("状態語だけのタイトルは空文字になる", () => {
    assert.equal(buildMarketQuery("【ジャンク】"), "");
  });
});

describe("closedSearchUrl", () => {
  it("検索語をエスケープする", () => {
    assert.ok(closedSearchUrl("Nikon F3").includes("p=Nikon%20F3"));
  });
});

describe("parseClosedPrices", () => {
  it("落札価格を拾う", () => {
    const html = `
      <li>落札価格 12,800円</li>
      <li>落札価格 9,500円</li>
      <li><span class="Product__priceValue">7,200円</span></li>
    `;
    assert.deepEqual(parseClosedPrices(html), [12800, 9500, 7200]);
  });

  it("該当が無ければ空配列(例外にしない)", () => {
    assert.deepEqual(parseClosedPrices("<html></html>"), []);
  });
});
