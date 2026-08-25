import assert from "node:assert/strict";
import { test } from "node:test";
import {
  RENDER_MIN_CLICKABLE,
  bidLandingVerdict,
  renderVerdict,
} from "./pageReady";

test("描画済みのページは rendered=true", () => {
  // 実測: 描画後の商品ページはクリック要素80超・input 複数
  assert.equal(renderVerdict({ clickable: 84, inputs: 3 }).rendered, true);
});

test("CSR 未マウントの骨組みは rendered=false", () => {
  // 実測(2026-08-25 ウォッチリスト): クリック要素3個・input 1個
  const v = renderVerdict({ clickable: 3, inputs: 1 });
  assert.equal(v.rendered, false);
  assert.match(v.reason, /CSR/);
});

test("閾値は実測値に固定されている", () => {
  // 定数を使った境界テストは閾値を動かしても一緒に動くので落ちない。
  // 実測(未マウント3個 / 描画後80個超)から選んだ 5 をここで釘付けにする
  assert.equal(RENDER_MIN_CLICKABLE, 5);
  assert.equal(renderVerdict({ clickable: 4, inputs: 1 }).rendered, false);
  assert.equal(renderVerdict({ clickable: 5, inputs: 1 }).rendered, true);
});

test("閾値ちょうどは描画済み側に倒す(境界)", () => {
  assert.equal(
    renderVerdict({ clickable: RENDER_MIN_CLICKABLE, inputs: 1 }).rendered,
    true,
  );
  assert.equal(
    renderVerdict({ clickable: RENDER_MIN_CLICKABLE - 1, inputs: 1 }).rendered,
    false,
  );
});

test("input ゼロでクリック要素も少ないページは疑う", () => {
  const v = renderVerdict({ clickable: RENDER_MIN_CLICKABLE + 1, inputs: 0 });
  assert.equal(v.rendered, false);
  assert.match(v.reason, /input/);
});

test("input ゼロでもクリック要素が十分あれば描画済み扱い", () => {
  // input の無い一覧ページを未描画と誤報しないため
  assert.equal(
    renderVerdict({ clickable: RENDER_MIN_CLICKABLE * 2, inputs: 0 }).rendered,
    true,
  );
});

test("rendered=true のときの reason は空(レポートに出さない)", () => {
  assert.equal(renderVerdict({ clickable: 40, inputs: 2 }).reason, "");
});

const L = (url: string, priceInputCount = 1) =>
  bidLandingVerdict({ url, priceInputCount });

test("入札フォームに着いていれば ok", () => {
  assert.equal(L("https://auctions.yahoo.co.jp/jp/show/bid?aID=b123").ok, true);
});

test("入札履歴に着いたら ok=false — 2026-08-25 に実際に踏んだ罠", () => {
  const v = L("https://auctions.yahoo.co.jp/jp/show/bid_hist?aID=b123", 1);
  assert.equal(v.ok, false);
  assert.match(v.reason, /入札履歴/);
});

test("入札履歴の判定は入力欄の有無より優先される", () => {
  // 両方あてはまる入力。判定順を逆にすると reason が「入力欄が無い」になり、
  // 「押した先が違うページ」という一番大事な事実がレポートから消える
  const v = L("https://auctions.yahoo.co.jp/jp/show/bid_hist", 0);
  assert.equal(v.ok, false);
  assert.match(v.reason, /入札履歴/);
  assert.doesNotMatch(v.reason, /入力欄/);
});

test("入札額の入力欄が無い着地点は信用しない", () => {
  const v = L("https://auctions.yahoo.co.jp/jp/auction/b123", 0);
  assert.equal(v.ok, false);
  assert.match(v.reason, /入力欄/);
});

test("判定は安全側に非対称 — 疑わしい着地点は全部 ok=false", () => {
  const bad = [
    { url: "https://auctions.yahoo.co.jp/jp/show/bid_hist?aID=b1", n: 2 },
    { url: "https://auctions.yahoo.co.jp/jp/auction/b1", n: 0 },
    { url: "https://login.yahoo.co.jp/", n: 0 },
    { url: "", n: 0 },
  ];
  for (const { url, n } of bad) {
    assert.equal(L(url, n).ok, false, `${url} は信用してはいけない`);
  }
});
