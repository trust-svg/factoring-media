import assert from "node:assert/strict";
import { test } from "node:test";
import { CAROUSEL_ANCESTOR_SELECTOR, watchlistScopeVerdict } from "./watchlistScope";

test("2026-08-27 の実測どおりに除外できていれば合格", () => {
  // 実測: 商品リンク148本のうち130本がカルーセル、残り18本が本物の9商品
  const v = watchlistScopeVerdict({ total: 148, kept: 18, carouselContainers: 3 });
  assert.equal(v.ok, true);
  assert.equal(v.reason, "");
});

test("カルーセルがあるのに1本も除外していなければ不合格", () => {
  // ⚠️ ここが効かないと、クラス名が変わった日に混入が黙って戻る
  const v = watchlistScopeVerdict({ total: 148, kept: 148, carouselContainers: 3 });
  assert.equal(v.ok, false);
  assert.match(v.reason, /1本も除外していない/);
});

test("カルーセルが無いページなら、除外0でも合格", () => {
  // 「カルーセルが無い」と「除外条件が壊れた」を混同しない。
  // 混同すると、カルーセルの無い日に同期が全部止まる
  const v = watchlistScopeVerdict({ total: 18, kept: 18, carouselContainers: 0 });
  assert.equal(v.ok, true);
});

test("拾えた分が全部カルーセルなら不合格", () => {
  // 一覧側の DOM が変わったケース。0件を「空のウォッチリスト」と読ませない
  const v = watchlistScopeVerdict({ total: 130, kept: 0, carouselContainers: 3 });
  assert.equal(v.ok, false);
  assert.match(v.reason, /全部カルーセルの中/);
});

test("商品リンクが0本のときは、この判定では不合格にしない", () => {
  // 「1本も無い」の扱いは呼び出し側(scrapeWatchlistPage)の責務。
  // ここで先に不合格にすると、理由が「除外条件が効いていない」に化ける
  assert.equal(watchlistScopeVerdict({ total: 0, kept: 0, carouselContainers: 3 }).ok, true);
  assert.equal(watchlistScopeVerdict({ total: 0, kept: 0, carouselContainers: 0 }).ok, true);
});

test("1本でも除外できていれば「効いていない」とは言わない", () => {
  const v = watchlistScopeVerdict({ total: 148, kept: 147, carouselContainers: 3 });
  assert.equal(v.ok, true);
});

test("除外セレクタは前方一致(完全一致のクラスは存在しない)", () => {
  // 定数を参照するだけのテストは、定数を変えても一緒に動いて落ちない。
  // 実測したクラス名の形をここで釘付けにする
  assert.equal(CAROUSEL_ANCESTOR_SELECTOR, '[class*="gv-Carousel"]');
  // 実物は gv-Carousel__button--WaNfn7XeNIprzkgpczEQ のようにハッシュが付く
  assert.doesNotMatch(CAROUSEL_ANCESTOR_SELECTOR, /class=/);
  assert.match(CAROUSEL_ANCESTOR_SELECTOR, /class\*=/);
});
