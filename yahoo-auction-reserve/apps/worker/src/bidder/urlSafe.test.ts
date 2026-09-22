import assert from "node:assert/strict";
import { test } from "node:test";
import { REDACTED, SAFE_QUERY_KEYS, redactUrl } from "./urlSafe";

test("クエリの無い URL はそのまま", () => {
  assert.equal(
    redactUrl("https://auctions.yahoo.co.jp/jp/auction/b1241524271"),
    "https://auctions.yahoo.co.jp/jp/auction/b1241524271",
  );
});

test("許可した名前の値は残る(どのページか分かる必要がある)", () => {
  assert.equal(
    redactUrl("https://auctions.yahoo.co.jp/jp/show/mystatus?select=watchlist"),
    "https://auctions.yahoo.co.jp/jp/show/mystatus?select=watchlist",
  );
});

test("許可していない名前の値は伏せる", () => {
  const out = redactUrl("https://login.yahoo.co.jp/config/login?.done=https%3A%2F%2Fx&crumb=abc123");
  assert.equal(out, `https://login.yahoo.co.jp/config/login?.done=${REDACTED}&crumb=${REDACTED}`);
  assert.doesNotMatch(out, /abc123/);
});

test("知らない名前は既定で伏せる(列挙漏れで漏れない)", () => {
  // ⚠️ 危険な名前を並べて伏せる方式だと、ここが通ってしまう
  const out = redactUrl("https://auctions.yahoo.co.jp/x?未知のパラメータ=himitsu");
  assert.doesNotMatch(out, /himitsu/);
  assert.match(out, /\*\*\*/);
});

test("フラグメントは落とす", () => {
  const out = redactUrl("https://auctions.yahoo.co.jp/x#access_token=himitsu");
  assert.equal(out, "https://auctions.yahoo.co.jp/x");
  assert.doesNotMatch(out, /himitsu/);
});

test("許可名と非許可名が混ざっても非許可だけ伏せる", () => {
  const out = redactUrl("https://auctions.yahoo.co.jp/x?select=watchlist&crumb=himitsu&page=2");
  assert.match(out, /select=watchlist/);
  assert.match(out, /page=2/);
  assert.doesNotMatch(out, /himitsu/);
});

test("パースできない文字列は丸ごと伏せる", () => {
  // 中身が分からないものを出さない。素通しさせない
  assert.equal(redactUrl("/jp/show/watchlist?crumb=himitsu"), REDACTED);
  assert.equal(redactUrl(""), REDACTED);
});

test("許可リストは狭い(値を出してよい名前だけ)", () => {
  // 定数を使った判定だけだと許可リストを広げても落ちない。実物を釘付けにする
  assert.equal(SAFE_QUERY_KEYS.has("select"), true);
  assert.equal(SAFE_QUERY_KEYS.has("watchclosed"), true);
  for (const dangerous of ["crumb", ".crumb", ".done", "token", "code", "state", "sig"]) {
    assert.equal(SAFE_QUERY_KEYS.has(dangerous), false, `${dangerous} を許可してはいけない`);
  }
});
