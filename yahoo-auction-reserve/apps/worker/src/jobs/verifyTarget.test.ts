import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// 生存確認(verifySession)を **どのページで行うか** を固定する。
//
// 2026-08-30 まで確認先は「予約中の商品ページ」だった。商品ページは新UI(CSR)
// なので `loginLink` も `loggedInIndicator` も 0件になり、ログイン中と失効が
// 同じ見た目になる。結果 26時間で4回中4回 UNKNOWN = 確認が一度も判定して
// いなかった。「落ちようがない検証」そのものだったので、両極を実測できている
// ウォッチリストへ移した。
//
// verifySession.ts は prisma / Playwright を直に握っていて実行できないため、
// ここではソース上の事実だけを見る。
const VERIFY_SRC = readFileSync(join(__dirname, "verifySession.ts"), "utf8");
const WATCHLIST_SRC = readFileSync(join(__dirname, "watchlist.ts"), "utf8");

describe("生存確認の確認先", () => {
  it("ウォッチリスト同期と同じ URL 定数を参照している", () => {
    // 片方だけ URL を直して気づかない事故を防ぐ。ここが literal に戻ると
    // 「同期は新URL・確認は旧URL」が静かに成立する。
    assert.match(
      VERIFY_SRC,
      /const VERIFY_TARGET_URL = WATCHLIST_URL_CANDIDATES\[0\]/,
      "確認先が WATCHLIST_URL_CANDIDATES から取られていない",
    );
    assert.match(
      WATCHLIST_SRC,
      /WATCHLIST_URL_CANDIDATES = \[[\s\S]*?"https:\/\/auctions\.yahoo\.co\.jp\/my\/watchlist"/,
      "同期側の先頭がウォッチリストの URL ではない",
    );
  });

  it("verifySession が自前のヤフオク URL を持っていない", () => {
    // FALLBACK_URL(トップページ)の復活防止。トップページは両極を実測して
    // いないので、判定できないまま「確認した」ことになる。
    const literals = VERIFY_SRC.match(/"https:\/\/[^"]*yahoo[^"]*"/g) ?? [];
    assert.deepEqual(literals, [], `URL が直書きされている: ${literals.join(", ")}`);
  });

  it("予約中の商品ページを開きに行かない", () => {
    assert.ok(
      !VERIFY_SRC.includes("auctionUrl"),
      "商品ページ(auctionUrl)を確認先にする経路が残っている",
    );
  });
});
