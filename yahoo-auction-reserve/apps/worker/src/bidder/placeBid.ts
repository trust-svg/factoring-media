import type { Page } from "playwright";
import { captureConfirmScreen } from "./diagnose";
import { submitTargetVerdict } from "./probeSafety";
import { selectors } from "./selectors";

export type BidResult =
  | { outcome: "SUCCESS" }
  | { outcome: "SESSION_EXPIRED" }
  | { outcome: "PAGE_ERROR"; detail: string }
  | { outcome: "TIMEOUT"; detail: string }
  /** テスト実行。確認画面まで到達し、4点ガードも通ったが確定は押していない */
  | { outcome: "DRY_RUN"; detail: string };

// 商品ページを開いた状態の page に対して、上限額で入札を確定させる。
// ここは P0 検証で実フローに合わせて必ず調整すること(設計 §13)。
//
// `dryRun: true` のときは **確定ボタンを押す直前で止める**。止める位置は
// submitTargetVerdict の判定より **後** に置いてある。判定より前で返すと
// 「確認画面に着けていないのに DRY_RUN 成功」になり、テスト実行が
// 一番確かめたいこと(本番なら正しいボタンを押せたか)を確かめないまま
// 合格を出す。DRY_RUN が返ったということは4点ガードを全部通ったということ。
export async function placeBid(
  page: Page,
  auctionUrl: string,
  amount: number,
  timeoutMs = 15_000,
  opts: { dryRun?: boolean } = {},
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
    // ⚠️ 2026-08-28 実測: 商品ページ・入札フォーム・確認画面の3画面すべてが
    // **同じ URL**(全部モーダル)。つまり下の `navigated` は常に false で、
    // 「遷移したから別の画面だ」という判断材料は最後まで存在しない。
    // しかも裏の商品ページの「入札する」ボタン2件は確認画面表示中も
    // DOM に残る。セレクタが緩いとそれを押して SUCCESS を返す
    // = **入札していないのに成功報告**(予約が空振りしても誰も気づかない)。
    //
    // そこで「確認画面に着いた」ことを別々の根拠で確かめてから押す。
    // 判定そのものは probeSafety.ts の submitTargetVerdict に集約:
    //   - found         : 確定ボタンが見つかる
    //   - formStillOpen : #inputPrice が消えている(着地の唯一の positive な証拠)
    //   - label         : ラベルが「入札する」ちょうど(=裏のボタン)ではない
    //   - sameAsBidButton: 最初に押した入札ボタンと別要素
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
    // 確認画面に進むと入札額の入力欄は DOM から消える(地雷12c)。
    // 数え損ねたときは「まだ残っている」= 止める側に倒す。
    const formStillOpen = await page
      .locator(selectors.priceInput)
      .count()
      .then((n) => n > 0)
      .catch(() => true);
    // ラベルが取れなかったときも止める側(空文字は「入札する」を含まない)。
    const label = submitHandle
      ? ((await submitButton.textContent({ timeout: timeoutMs }).catch(() => "")) ?? "")
      : "";

    const verdict = submitTargetVerdict({
      found: submitHandle !== null,
      navigated,
      sameAsBidButton,
      formStillOpen,
      label,
    });
    if (!verdict.safe) {
      // 押すのはもう諦めた後なので、ここで画面を1往復だけ計測して残す。
      // これが無いと「確定ボタンが見つからない」の1行しか残らず、
      // 文言が違うのか確認画面に着いていないのかを切り分けるために
      // オークションをもう1件使う羽目になる(2026-08-28 に実際に起きた)。
      const snapshot = await captureConfirmScreen(page);
      return {
        outcome: "PAGE_ERROR",
        detail: `確定を中止: ${verdict.reason} ${snapshot}`,
      };
    }
    // --- ここから先を実行するかどうかが、テスト実行と本番の唯一の差 ---
    if (opts.dryRun) {
      return {
        outcome: "DRY_RUN",
        detail:
          `テスト実行のため確定を押していません。` +
          `確認画面には到達済(入札額の入力欄が消えている)。` +
          `押すはずだったボタン: ${JSON.stringify(label.trim())} / 入札額: ${amount}円`,
      };
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
