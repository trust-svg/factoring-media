import { test } from "node:test";
import assert from "node:assert/strict";
import { parseAuctionPage } from "./scraper";
import { judgeBuyNow } from "./judgement";

const URL = "https://page.auctions.yahoo.co.jp/jp/auction/x1234567890";

function pageWithJson(obj: unknown): string {
  return `<html><head><meta property="og:title" content="テスト商品"></head><body>
<script id="__NEXT_DATA__" type="application/json">${JSON.stringify(obj)}</script>
</body></html>`;
}

// --- パース -------------------------------------------------------------

test("埋め込みJSONの即決価格を読む", () => {
  const html = pageWithJson({ props: { item: { price: 2000, bidOrBuyPrice: 8000 } } });
  const info = parseAuctionPage(html, URL);
  assert.equal(info.currentPrice, 2000);
  assert.equal(info.buyNowPrice, 8000);
});

test("同名キーが boolean で先に見つかっても、数値の即決価格まで探し続ける", () => {
  // ヤフオクの埋め込みJSONには bidorbuy が「即決あり/なし」の真偽値で
  // 入っていることがある。1件目で打ち切ると即決価格を取りこぼす。
  const html = pageWithJson({
    flags: { bidorbuy: true },
    detail: { bidorbuy: 12000 },
  });
  assert.equal(parseAuctionPage(html, URL).buyNowPrice, 12000);
});

test("即決価格 0 は「即決なし」であって 0円即決ではない", () => {
  const html = pageWithJson({ item: { bidOrBuyPrice: 0 } });
  assert.equal(parseAuctionPage(html, URL).buyNowPrice, undefined);
});

test("即決価格が無い出品は undefined のまま(0 を作らない)", () => {
  const html = pageWithJson({ item: { price: 1500 } });
  const info = parseAuctionPage(html, URL);
  assert.equal(info.buyNowPrice, undefined);
  assert.equal(info.currentPrice, 1500);
});

test("埋め込みJSONが無くても本文から即決価格を拾う", () => {
  const html = `<html><body>
    <p>現在価格 1,200円</p>
    <p>即決価格 9,800円</p>
  </body></html>`;
  const info = parseAuctionPage(html, URL);
  assert.equal(info.currentPrice, 1200);
  assert.equal(info.buyNowPrice, 9800);
});

test("本文に即決の記載が無ければ現在価格を即決価格として拾わない", () => {
  const html = `<html><body><p>現在価格 1,200円</p></body></html>`;
  const info = parseAuctionPage(html, URL);
  assert.equal(info.buyNowPrice, undefined);
});

// --- 判定 ---------------------------------------------------------------

test("上限額が即決価格以上なら警告(入札した瞬間に即決成立するため)", () => {
  assert.equal(judgeBuyNow(8000, 8000).level, "warn");
  assert.equal(judgeBuyNow(9000, 8000).level, "warn");
  assert.match(judgeBuyNow(9000, 8000).reasons[0], /即決成立/);
});

test("上限額が即決価格未満なら ok", () => {
  assert.equal(judgeBuyNow(7999, 8000).level, "ok");
});

test("即決価格が無いときは ok ではなく unknown(判断していないことを混ぜない)", () => {
  const j = judgeBuyNow(9999999, null);
  assert.equal(j.level, "unknown");
  assert.deepEqual(j.reasons, []);
});
