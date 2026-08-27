import type { Page } from "playwright";
import { type RenderVerdict, renderVerdict } from "./pageReady";

// 「描画が落ち着くまで待つ」処理。
//
// ⚠️ **プローブと本番の同期で必ず同じものを使う**。
//    2026-08-27 まで、待つ処理はプローブ(scripts/p0-probe.ts)にしか無く、
//    同期ジョブ(jobs/watchlist.ts)は `waitUntil: "domcontentloaded"` の直後に
//    読んでいた。ヤフオクの新UIは CSR なので、これは
//    「読むたびに違うものが見える」ことを意味する。実際、同じページで
//    プローブは商品リンク148本を見て、同期は回によって9〜33件しか見なかった。
//    しかも少なく見えた回も **成功として** 返るので、どの回が中途半端な
//    DOM を読んだのか事後には分からない。
//
// ⚠️ ここは「セレクタが合っているか」には答えない。答えるのは
//    「読む価値のある DOM がそこにあるか」だけ(pageReady.ts と同じ責務境界)。

export const SETTLE_POLL_MS = 400;
/** クリック要素の数がこの回数だけ連続で変わらなければ「落ち着いた」とみなす */
export const SETTLE_STABLE_ROUNDS = 3;
export const SETTLE_MAX_MS = 15_000;

export interface SettleResult {
  clickable: number;
  inputs: number;
  elapsedMs: number;
  verdict: RenderVerdict;
}

/**
 * クリック要素の数が増えなくなるまで待つ。
 * 待ち切れなくても例外にはしない — 判定は返り値の verdict で行う。
 */
export async function settlePage(page: Page): Promise<SettleResult> {
  // networkidle は「来たら儲けもの」。来なくても下のポーリングで進む
  await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => {});

  const started = Date.now();
  let stable = 0;
  let prev = -1;
  let clickable = 0;
  let inputs = 0;
  while (Date.now() - started < SETTLE_MAX_MS) {
    clickable = await page
      .locator("button, input[type=submit], input[type=button], a")
      .count()
      .catch(() => 0);
    inputs = await page.locator("input").count().catch(() => 0);
    if (clickable === prev) {
      stable += 1;
      if (stable >= SETTLE_STABLE_ROUNDS) break;
    } else {
      stable = 0;
      prev = clickable;
    }
    await page.waitForTimeout(SETTLE_POLL_MS);
  }

  return {
    clickable,
    inputs,
    elapsedMs: Date.now() - started,
    verdict: renderVerdict({ clickable, inputs }),
  };
}
