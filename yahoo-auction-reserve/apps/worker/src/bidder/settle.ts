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

/**
 * 入札の残り手順(入札ボタン→額入力→確認→確定)のために必ず残す時間。
 * 描画待ちにこれ以上使うと、終了間際の予約が待っている間に終わる。
 */
export const BID_STEPS_RESERVE_MS = 3_000;

/** 描画の落ち着きを測るときに数える「クリックできる要素」。 */
export const CLICKABLE_SELECTOR = "button, input[type=submit], input[type=button], a";

/**
 * 描画待ちに使ってよい時間。仕事は **残り時間で上限を切る** こと。
 *
 * ⚠️ `snipeSecondsBefore` は 5〜600秒(既定30)。5秒前に入札する予約で
 *    15秒待つと、**待っている間にオークションが終わる**。描画待ちを足す
 *    ときは必ずここを通す(「遅いから伸ばす」を無条件でやると、短い予約
 *    だけが黙って入札されなくなる)。
 * `remainingMs` を渡さない = 終了時刻が分からない場合だけ maxMs をそのまま使う。
 */
export function settleBudgetMs(args: { remainingMs?: number; maxMs?: number }): number {
  const max = args.maxMs ?? SETTLE_MAX_MS;
  if (args.remainingMs === undefined) return max;
  const usable = args.remainingMs - BID_STEPS_RESERVE_MS;
  if (usable <= 0) return 0;
  return Math.min(max, usable);
}

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
export async function settlePage(page: Page, maxMs = SETTLE_MAX_MS): Promise<SettleResult> {
  // networkidle は「来たら儲けもの」。来なくても下のポーリングで進む。
  // ⚠️ Playwright の `timeout: 0` は「即座に諦める」ではなく **無制限**。
  //    残り時間が無いときに 0 をそのまま渡すと、待ち時間を削るつもりで
  //    永久に待つ処理に化ける。0以下なら待たずに飛ばす。
  const idleMs = Math.min(5_000, Math.max(0, maxMs));
  if (idleMs > 0) {
    await page.waitForLoadState("networkidle", { timeout: idleMs }).catch(() => {});
  }

  const started = Date.now();
  let stable = 0;
  let prev = -1;
  let clickable = 0;
  let inputs = 0;
  // ⚠️ `while` ではなく `do`。予算0で1度も測らずに返すと、clickable=0 の
  //    「描画されていない」という **測っていない判定** を返してしまう。
  do {
    clickable = await page
      .locator(CLICKABLE_SELECTOR)
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
  } while (Date.now() - started < maxMs);

  return {
    clickable,
    inputs,
    elapsedMs: Date.now() - started,
    verdict: renderVerdict({ clickable, inputs }),
  };
}
