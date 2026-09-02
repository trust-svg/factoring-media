import { test } from "node:test";
import assert from "node:assert/strict";
import { formatBidEntrySnapshot, formatConfirmScreenSnapshot, normalizeLabels } from "./diagnose";

test("空白の潰し・重複除去・件数の上限", () => {
  const { labels, truncated } = normalizeLabels([
    "  入札する  ",
    "入札する",
    "\n入札\n する \n",
    "",
    "   ",
  ]);
  // 「入札する」と「入札 する」は別物として残す(空白の潰し方だけ揃える)
  assert.deepEqual(labels, ["入札する", "入札 する"]);
  assert.equal(truncated, false);
});

test("13件以上は切り、切ったことを申告する", () => {
  const raw = Array.from({ length: 20 }, (_, i) => `ボタン${i}`);
  const { labels, truncated } = normalizeLabels(raw);
  assert.equal(labels.length, 12);
  assert.equal(truncated, true);
});

test("長いラベルは省略記号付きで切る", () => {
  const { labels } = normalizeLabels(["あ".repeat(100)]);
  assert.equal(labels[0].length, 61); // 60文字 + …
  assert.ok(labels[0].endsWith("…"));
});

test("可視ボタンが0件でも「0件」と分かる形で出す", () => {
  // ⚠️ 空文字を返すと「計測できなかった」と区別が付かない。
  // 0件は「確認画面に着いていない」の強い証拠なので必ず言葉にする。
  const line = formatConfirmScreenSnapshot({
    url: "https://page.auctions.yahoo.co.jp/jp/auction/x1",
    priceInputCount: 1,
    submitSelectorHits: 0,
    labels: [],
    truncated: false,
  });
  assert.match(line, /可視ボタン0件/);
  assert.match(line, /入力欄=1件/);
  assert.match(line, /現行セレクタのヒット=0件/);
});

test("ラベルは引用符付きで出す(前後の空白や紛らわしい文字を見えるようにする)", () => {
  const line = formatConfirmScreenSnapshot({
    url: "https://page.auctions.yahoo.co.jp/jp/auction/x1",
    priceInputCount: 0,
    submitSelectorHits: 0,
    labels: ["入札する", "上記のガイドライン等、情報提供に同意して 入札する"],
    truncated: true,
  });
  assert.match(line, /"入札する"/);
  assert.match(line, /情報提供に同意して/);
  assert.ok(line.endsWith("…"), "切り落としたことが末尾で分かる");
});

// --- 入札ボタンが掴めなかったときの計測(2026-09-02 の実入札で必要になった) ---

test("「入札」を含む可視要素が0件でも、0件と分かる形で出す", () => {
  // ⚠️ 空文字にすると「計測できなかった」と区別が付かない。0件は
  // 「描画が終わっていない」「商品ページに居ない」の強い証拠なので言葉にする。
  const line = formatBidEntrySnapshot({
    url: "https://page.auctions.yahoo.co.jp/jp/auction/x1",
    title: "商品ページ",
    bidSelectorHits: 0,
    loginLinkHits: 0,
    clickable: 3,
    bidLikeLabels: [],
    truncated: false,
  });
  assert.ok(line.includes("(0件)"), line);
  assert.ok(line.includes("クリック要素=3個"), line);
});

test("要素の種類(button か a か)とパス名が読める形で残る", () => {
  // 旧UIの入札の入口は <a href="/jp/show/bid">。role=button のセレクタからは
  // 永久に見えないので、ここで種類が分からないと次の1回も無駄になる。
  const line = formatBidEntrySnapshot({
    url: "https://page.auctions.yahoo.co.jp/jp/auction/x1",
    title: "商品ページ",
    bidSelectorHits: 0,
    loginLinkHits: 0,
    clickable: 88,
    bidLikeLabels: ["<a /jp/show/bid> 入札する", "<a /jp/show/bid_hist> 入札履歴"],
    truncated: false,
  });
  assert.ok(line.includes("/jp/show/bid>"), line);
  assert.ok(line.includes("/jp/show/bid_hist>"), line);
});

test("URL とタイトルを載せる(別のページに居た場合の判別)", () => {
  const line = formatBidEntrySnapshot({
    url: "https://login.yahoo.co.jp/config/login",
    title: "ログイン - Yahoo! JAPAN",
    bidSelectorHits: 0,
    loginLinkHits: 2,
    clickable: 12,
    bidLikeLabels: [],
    truncated: false,
  });
  assert.ok(line.includes("login.yahoo.co.jp"), line);
  assert.ok(line.includes("ログイン - Yahoo! JAPAN"), line);
  assert.ok(line.includes("ログインリンク=2件"), line);
});
