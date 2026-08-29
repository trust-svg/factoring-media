import type { Page } from "playwright";
import { bidHistoryUrl, bidHistoryVerdict, type ResultVerdict } from "./bidHistory";
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
    // ⚠️ `<input type="submit">` は textContent が空。ラベルは value に入る。
    // textContent だけを見ると、正しく確定ボタンを掴んでいるのに毎回
    // 「ラベルが取れない」でガードに落ちて入札が成立しなくなる。
    const label = submitHandle
      ? ((await submitButton
          .evaluate((el) => {
            const node = el as unknown as { value?: unknown; textContent: string | null };
            return typeof node.value === "string" && node.value ? node.value : (node.textContent ?? "");
          })
          .catch(() => "")) ?? "")
      : "";
    // 確定ボタンに当たった数。1件でないなら、押す前に人間が知る必要がある
    // (2026-08-28 は 0件で2回失敗した。次は「本当に1件か」を DRY_RUN で確かめる)
    const submitHits = await page.locator(selectors.bidSubmitButton).count().catch(() => -1);

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
          `押すはずだったボタン: ${JSON.stringify(label.trim())}` +
          `(セレクタのヒット=${submitHits}件${submitHits === 1 ? "" : " ⚠️1件でない"})` +
          ` / 入札額: ${amount}円`,
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

// 終了後の勝敗を判定する。
//
// ⚠️ 見るのは **商品ページではなく入札履歴ページ**。
// 2026-08-29 実測(n1242036522): 終了後の商品ページに載っている状態表示は
// 「このオークションは終了しています」の1行だけで、落札者名も
// 「あなたが落札しました」も「高値更新」も無い。**商品ページを読む限り
// WON と LOST は区別できず**、旧実装は必ず UNKNOWN を返していた。
// (その UNKNOWN を monitor が LOST に畳んでいたので、落札しても
//  「落札ならず」と通知される経路だった。理由は bidHistory.ts に記録)
//
// 判定そのものは bidHistory.ts の bidHistoryVerdict に集約する
// (ブラウザ無しでテストできる形にして、実データの行をテストに固定してある)。
export async function checkResult(
  page: Page,
  auctionUrl: string,
): Promise<{ verdict: ResultVerdict; reason: string }> {
  const url = bidHistoryUrl(auctionUrl);
  if (!url) {
    return { verdict: "UNKNOWN", reason: `商品URLから入札履歴URLを作れない: ${auctionUrl}` };
  }
  try {
    await page.goto(url, { waitUntil: "domcontentloaded" });
    // 自分の表示名。伏字にならないのは自分の行だけなので、これが鍵になる。
    const myDisplayName = await page
      .locator(selectors.loggedInIndicator)
      .first()
      .innerText()
      .catch(() => "");
    const rows = await page.locator(selectors.bidHistoryRow).allInnerTexts().catch(() => []);
    return bidHistoryVerdict({ rows, myDisplayName });
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    return { verdict: "UNKNOWN", reason: `入札履歴ページを読めなかった: ${detail}` };
  }
}
