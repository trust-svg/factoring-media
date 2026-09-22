import { test } from "node:test";
import assert from "node:assert/strict";
import { parseAuctionPage, sellerNameCandidates } from "./scraper";

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

// --- テキストのフォールバック -------------------------------------------
//
// 2026-08-29 実測の生HTML(o1242306599)。ラベルと数字の間にタグが 90 文字以上
// 挟まり、クラス名に数字(sc-1f0603b0-1)が入り、数字と「円」の間に
// HTMLコメントが入る。生HTMLに正規表現を当てていた頃はこれで全滅していた。
const REAL_MARKUP = `<html><body>
<p>現在JavaScriptの設定が無効になっています。すべての機能を利用するには設定を有効にしてください。</p>
<dl>
  <dt class="KB gv-u-colorContentOnSurfaceVariant--iGAjy0BdpomNMjXrpED_">現在</dt>
  <dd class="sc-1f0603b0-1 eNGAca"><span class="sc-1f0603b0-3 eGrksu">510<!-- -->円</span><span>（税0円）</span></dd>
  <dt class="KB gv-u-colorContentOnSurfaceVariant--iGAjy0BdpomNMjXrpED_">即決</dt>
  <dd class="sc-1f0603b0-1 eNGAca"><span class="sc-1f0603b0-3 eGrksu">44,000<!-- -->円</span><span>（税0円）</span></dd>
</dl>
</body></html>`;

test("埋め込みJSONが無くても、実際のマークアップから現在価格と即決価格を拾う", () => {
  const info = parseAuctionPage(REAL_MARKUP, URL);
  assert.equal(info.currentPrice, 510);
  assert.equal(info.buyNowPrice, 44000);
});

test("「現在JavaScriptの設定が…」を現在価格と読み違えない", () => {
  // 「現在」で始まる無関係な文が価格より前に出る。数字までの距離を
  // 詰めてあるので当たらないはずだが、緩めた日に壊れるので固定しておく。
  const html = `<html><body>
    <p>現在JavaScriptの設定が無効になっています。有効にしてください。</p>
    <p>現在 <span>1,200</span> 円</p>
  </body></html>`;
  assert.equal(parseAuctionPage(html, URL).currentPrice, 1200);
});

test("script の中の文字列を本文と混ぜない", () => {
  // 埋め込みJSONは別経路で読む。本文テキストに混ぜると
  // `"price":999` のような値が価格の正規表現に拾われる。
  const html = `<html><body>
    <script>var dummy = "現在 999 円 / 即決 999 円";</script>
    <p>現在 510 円</p>
  </body></html>`;
  const info = parseAuctionPage(html, URL);
  assert.equal(info.currentPrice, 510);
  assert.equal(info.buyNowPrice, undefined);
});

// --- 税込 / 税抜 ---------------------------------------------------------

test("即決価格は税込(taxinBidorbuy)を優先する", () => {
  // 2026-08-29 実測(n1242036522・ストア出品): 表示は「即決 8,910円(税込)」。
  // bidOrBuyPrice は税抜なので、そのまま出すと支払額を 10% 低く見せる。
  const html = pageWithJson({
    item: { currentPrice: 1, bidOrBuyPrice: 8100, taxRate: 10, taxinBidorbuy: 8910 },
  });
  assert.equal(parseAuctionPage(html, URL).buyNowPrice, 8910);
});

test("税キーが無い出品(個人)は bidOrBuyPrice をそのまま使う", () => {
  // 2026-08-29 実測(o1242306599・個人出品): 税キーが無く「税0円」表示。
  const html = pageWithJson({ item: { currentPrice: 510, bidOrBuyPrice: 44000 } });
  assert.equal(parseAuctionPage(html, URL).buyNowPrice, 44000);
});

// --- 出品者名: 他の出品者の入れ物が同居するケース --------------------------
//
// 2026-09-02 時点の DB に `buo********` / `piz********` という値が
// 出品者名として保存されていた。これはヤフオクが **入札者**の ID を
// 伏せる形で、出品者の表示名ではない(出品者は評価リンクに ID がそのまま出る)。
// つまり出品者以外の入れ物を掴んでいた。
//
// ⚠️ ここの JSON はヤフオクの実物ではなく手書き。実ページの形は
// P0 プローブの「出品者名の候補」で確かめる(推測でキー名を足さないこと)。

test("おすすめ枠の別出品者より、対象オークションの入れ物が勝つ", () => {
  const html = pageWithJson({
    props: {
      // ⚠️ 並び順に意味がある。探索は stack.pop() の深さ優先なので
      // **後ろに書いたほうが先に訪問される**。木全体から拾う実装では
      // ここで `recommend` が勝って「よその店」が返る(変異テストで確認済み:
      // auctionId で絞る処理を外すとこのテストだけが落ちる)。
      // 本命を先に書くと、絞らなくても偶然正解して落ちようがない検証になる。
      item: {
        auctionId: "x1234567890",
        currentPrice: 1,
        seller: { displayName: "本命ストア" },
      },
      recommend: {
        items: [
          { auctionId: "z9999999999", seller: { displayName: "よその店" } },
        ],
      },
    },
  });
  assert.equal(parseAuctionPage(html, URL).sellerName, "本命ストア");
});

test("伏字の ID は出品者名として採らない(他に候補が無ければ空)", () => {
  const html = pageWithJson({
    props: { item: { currentPrice: 1, seller: { displayName: "buo********" } } },
  });
  assert.equal(parseAuctionPage(html, URL).sellerName, undefined);
});

test("伏字が先に見つかっても、伏字でない候補があればそちらを採る", () => {
  const html = pageWithJson({
    props: {
      item: {
        auctionId: "x1234567890",
        currentPrice: 1,
        seller: { displayName: "piz********", name: "きちんとした店名" },
      },
    },
  });
  assert.equal(parseAuctionPage(html, URL).sellerName, "きちんとした店名");
});

test("sellerNameCandidates は採用しなかった候補も伏字の印つきで返す", () => {
  const html = pageWithJson({
    props: {
      recommend: { items: [{ auctionId: "z9999999999", seller: { displayName: "よその店" } }] },
      item: { auctionId: "x1234567890", seller: { displayName: "buo********", name: "本命ストア" } },
    },
  });
  const got = sellerNameCandidates(html, URL);
  const masked = got.find((c) => c.value === "buo********");
  assert.ok(masked, "伏字の候補が候補一覧に出ること");
  assert.equal(masked?.masked, true);
  assert.ok(
    got.some((c) => c.value === "本命ストア" && c.scope.startsWith("auctionId一致")),
    "対象オークションの入れ物から拾った候補には、そう分かる印が付くこと",
  );
});
