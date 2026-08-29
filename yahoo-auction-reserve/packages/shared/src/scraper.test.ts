import { test } from "node:test";
import assert from "node:assert/strict";
import { parseAuctionPage } from "./scraper";

const URL = "https://page.auctions.yahoo.co.jp/jp/auction/x1234567890";

function pageWithJson(obj: unknown): string {
  return `<html><head><meta property="og:title" content="テスト商品"></head><body>
<script id="__NEXT_DATA__" type="application/json">${JSON.stringify(obj)}</script>
</body></html>`;
}

// --- 出品者名 -----------------------------------------------------------
//
// 2026-08-29 の実測(n1242036522)で、入札後の商品ページの出品者名が
// **ログイン中の自分の表示名**になっていた。ページには買い手(自分)の
// displayName も埋まっているので、木全体から displayName を拾うと
// どちらが勝つかは探索順まかせになる。

test("出品者名は出品者の入れ物から取る(自分の表示名を出品者にしない)", () => {
  const html = pageWithJson({
    props: {
      login: { displayName: "Royal Coin Japan" }, // ← 自分
      item: {
        currentPrice: 1,
        seller: { displayName: "ReRe オークションストア", id: "rere_store" },
      },
    },
  });
  assert.equal(parseAuctionPage(html, URL).sellerName, "ReRe オークションストア");
});

test("出品者の入れ物が無ければ sellerId まで。自分の displayName は採らない", () => {
  const html = pageWithJson({
    props: {
      login: { displayName: "Royal Coin Japan" },
      item: { currentPrice: 1, sellerId: "rere_store" },
    },
  });
  assert.equal(parseAuctionPage(html, URL).sellerName, "rere_store");
});

test("出品者の手がかりが何も無ければ undefined(他人の名前で埋めない)", () => {
  const html = pageWithJson({
    props: { login: { displayName: "Royal Coin Japan" }, item: { currentPrice: 1 } },
  });
  assert.equal(parseAuctionPage(html, URL).sellerName, undefined);
});

// --- キー配列は優先順位である -------------------------------------------

test("現在価格は汎用の price より currentPrice を優先する", () => {
  // 送料や関連商品にも `price` は付く。優先順位が効いていないと、
  // 探索でたまたま先に当たったほうが現在価格になる。
  const html = pageWithJson({
    shipping: { price: 500 },
    item: { currentPrice: 1200 },
  });
  assert.equal(parseAuctionPage(html, URL).currentPrice, 1200);
});

test("優先度の高いキーが無ければ後ろのキーに落ちる", () => {
  const html = pageWithJson({ item: { price: 1200 } });
  assert.equal(parseAuctionPage(html, URL).currentPrice, 1200);
});
