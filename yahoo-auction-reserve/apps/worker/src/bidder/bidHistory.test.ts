import assert from "node:assert/strict";
import { test } from "node:test";
import { bidHistoryUrl, bidHistoryVerdict } from "./bidHistory";

// 2026-08-29 に n1242036522 の入札履歴ページから実際に読んだ行(そのまま)。
const REAL_ROWS = [
  "入札履歴 TASCAM MD-350 タスカム MDデッキ レコーダー 業務用 音響機材 中古 訳あり O11495517 商品ページに戻る",
  "入札者の順位 2件 すべての入札履歴 入札者の表示について",
  "入札者 / 評価 入札額 個数 最後に手動入札した時間",
  "ymb******** / 評価：238 最高額入札者 21 円 1 8月 29日 21時 32分",
  "Royal Coin Japan / 評価：186 （評価の詳細） 11 円 1 8月 29日 0時 40分",
];

test("実データ: 自分の行に最高額入札者が無ければ LOST", () => {
  const v = bidHistoryVerdict({ rows: REAL_ROWS, myDisplayName: "Royal Coin Japan" });
  assert.equal(v.verdict, "LOST");
});

test("実データ: 落札していれば自分の行に最高額入札者が付く(WON)", () => {
  // 上の実データの立場を入れ替えただけ。同じページの ymb 行が陽性対照。
  const rows = [
    ...REAL_ROWS.slice(0, 3),
    "Royal Coin Japan / 評価：186 最高額入札者 21 円 1 8月 29日 21時 32分",
    "ymb******** / 評価：238 （評価の詳細） 11 円 1 8月 29日 0時 40分",
  ];
  assert.equal(bidHistoryVerdict({ rows, myDisplayName: "Royal Coin Japan" }).verdict, "WON");
});

test("表示名が読めなければ UNKNOWN(LOST に倒さない)", () => {
  const v = bidHistoryVerdict({ rows: REAL_ROWS, myDisplayName: "   " });
  assert.equal(v.verdict, "UNKNOWN");
  assert.match(v.reason, /表示名/);
});

test("入札者の行が1件も無ければ UNKNOWN", () => {
  const v = bidHistoryVerdict({ rows: ["入札履歴", ""], myDisplayName: "Royal Coin Japan" });
  assert.equal(v.verdict, "UNKNOWN");
});

test("自分の行が無ければ UNKNOWN(入札できていなかった場合)", () => {
  const v = bidHistoryVerdict({ rows: REAL_ROWS, myDisplayName: "別のだれか" });
  assert.equal(v.verdict, "UNKNOWN");
  assert.match(v.reason, /自分/);
});

test("自分の行が2件に当たったら特定できないので UNKNOWN", () => {
  const rows = [
    "入札者 / 評価 入札額 個数 最後に手動入札した時間",
    "Royal Coin Japan / 評価：186 最高額入札者 21 円 1 8月 29日 21時 32分",
    "Royal Coin Japan の中古品を探す / 評価：1 11 円 1 8月 29日 0時 40分",
  ];
  const v = bidHistoryVerdict({ rows, myDisplayName: "Royal Coin Japan" });
  assert.equal(v.verdict, "UNKNOWN");
  assert.match(v.reason, /2件/);
});

test("ヘッダ行の「最高額入札者」は自分の行と取り違えない", () => {
  // ヘッダに文言が入っても、自分の名前を含まない行は候補にならない
  const rows = [
    "入札者 / 評価 入札額 最高額入札者",
    "Royal Coin Japan / 評価：186 （評価の詳細） 11 円",
  ];
  assert.equal(bidHistoryVerdict({ rows, myDisplayName: "Royal Coin Japan" }).verdict, "LOST");
});

test("入札履歴 URL は商品URLから組み立てる", () => {
  assert.equal(
    bidHistoryUrl("https://auctions.yahoo.co.jp/jp/auction/n1242036522"),
    "https://auctions.yahoo.co.jp/jp/show/bid_hist?aID=n1242036522",
  );
  assert.equal(bidHistoryUrl("https://example.com/not-an-auction"), null);
});
