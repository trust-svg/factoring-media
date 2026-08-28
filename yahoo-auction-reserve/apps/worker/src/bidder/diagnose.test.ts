import { test } from "node:test";
import assert from "node:assert/strict";
import { formatConfirmScreenSnapshot, normalizeLabels } from "./diagnose";

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
