import type { Page } from "playwright";
import { submitTargetVerdict } from "./probeSafety";
import { selectors } from "./selectors";

export type BidResult =
  | { outcome: "SUCCESS" }
  | { outcome: "SESSION_EXPIRED" }
  | { outcome: "PAGE_ERROR"; detail: string }
  | { outcome: "TIMEOUT"; detail: string };

// 商品ページを開いた状態の page に対して、上限額で入札を確定させる。
// ここは P0 検証で実フローに合わせて必ず調整すること(設計 §13)。
export async function placeBid(
  page: Page,
  auctionUrl: string,
  amount: number,
  timeoutMs = 15_000,
): Promise<BidResult> {
  try {
    if (page.url() !== auctionUrl) {
      await page.goto(auctionUrl, { waitUntil: "domcontentloaded" });
    }

    // ログイン確認: ログインリンクが見えている=未ログイン
    if (await page.locator(selectors.loginLink).first().isVisible().catch(() => false)) {
      return { outcome: "SESSION_EXPIRED" };
    }

    const bidButton = page.locator(selectors.bidButton).first();
    // 確定直前のガードで「同じ要素か」を見るために、押す前に掴んでおく
    const bidHandle = await bidButton.elementHandle({ timeout: timeoutMs });
    const urlBeforeBid = page.url();
    await bidButton.click({ timeout: timeoutMs });

    await page.locator(selectors.priceInput).first().fill(String(amount), {
      timeout: timeoutMs,
    });
    await page.locator(selectors.bidConfirmButton).first().click({ timeout: timeoutMs });

    // --- 確認画面 → 確定。ここから先は取り消せない ---
    //
    // ⚠️ 2026-08-28 実測: 入札フォームは **モーダル** で URL が変わらない。
    // つまり下の `navigated` は常に false で、「遷移したから別要素」という
    // 逃げ道は存在しない。bidSubmitButton が bidButton と同じ文字列のままだと、
    // モーダルの裏に残っている商品ページの「入札する」を掴んで
    // sameAsBidButton=true になり、確定は **必ず** 中止される。
    // 安全側の停止だが、この状態では入札は一度も成立しない。
    // 確認画面の確定ボタンの実体を P0 で取るまで本番稼働させないこと。
    //
    // selectors.bidSubmitButton は bidButton と文字列が同一なので、
    // 確認クリックが遷移を起こしていないと、商品ページの「入札する」を
    // もう一度押して SUCCESS を返してしまう(入札していないのに成功報告)。
    // 押す前に「本当に別の要素か」を確かめる。判定は probeSafety.ts。
    const submitButton = page.locator(selectors.bidSubmitButton).first();
    const submitHandle = await submitButton
      .elementHandle({ timeout: timeoutMs })
      .catch(() => null);
    const navigated = page.url() !== urlBeforeBid;
    // 遷移していれば比較しない(ハンドルが無効になっていて必ず失敗するため)。
    // 遷移していない場合だけ比較し、比較そのものが失敗したら止める側に倒す。
    const sameAsBidButton =
      navigated || !submitHandle
        ? false
        : await page
            .evaluate(([a, b]) => a === b, [bidHandle, submitHandle])
            .catch(() => true);

    const verdict = submitTargetVerdict({
      found: submitHandle !== null,
      navigated,
      sameAsBidButton,
    });
    if (!verdict.safe) {
      return { outcome: "PAGE_ERROR", detail: `確定を中止: ${verdict.reason}` };
    }
    await submitButton.click({ timeout: timeoutMs });

    // 確定後の遷移完了を待つ
    await page.waitForLoadState("domcontentloaded", { timeout: timeoutMs });
    return { outcome: "SUCCESS" };
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    if (/Timeout/i.test(detail)) {
      return { outcome: "TIMEOUT", detail };
    }
    return { outcome: "PAGE_ERROR", detail };
  }
}

// 終了後の商品ページから勝敗を判定する
export async function checkResult(
  page: Page,
  auctionUrl: string,
): Promise<"WON" | "LOST" | "UNKNOWN"> {
  try {
    await page.goto(auctionUrl, { waitUntil: "domcontentloaded" });
    if (await page.locator(selectors.wonIndicator).first().isVisible().catch(() => false)) {
      return "WON";
    }
    if (await page.locator(selectors.outbidIndicator).first().isVisible().catch(() => false)) {
      return "LOST";
    }
    return "UNKNOWN";
  } catch {
    return "UNKNOWN";
  }
}
