import type { Page } from "playwright";
import { selectors } from "./selectors";

// 確定ガードが落ちたときに「確認画面に何があったか」を残すための計測。
//
// なぜ要るか: 2026-08-28 のテスト実行は
// 「確定ボタンが見つからない」で止まったが、**残った記録はその1行だけ**
// だった。確定ボタンのセレクタは実ラベルを1商品でしか実測していない
// (selectors.ts の 🟡)。文言が商品によって変わるのか、そもそも確認画面に
// 着いていないのかを、この1行から切り分ける方法が無い。
//
// つまり原因を知るには **もう一度オークションを1件使って同じ1行を得る**
// しかない状態だった。ガードが落ちた時点で押すのはもう諦めているので、
// そこで画面のボタンのラベルを数えて残しておけば、次の1回で決着がつく。
//
// ⚠️ 残すのはボタンのラベルと件数だけ。本文・Cookie・アカウント情報は
// 触らない(設計 §8)。

/** detail に載せるラベルの上限。多いと通知が読めなくなる */
const MAX_LABELS = 12;
/** ラベル1件の上限文字数 */
const MAX_LABEL_CHARS = 60;
/** 計測そのものが固まって終了時刻を食い潰さないための上限 */
const CAPTURE_TIMEOUT_MS = 3_000;

export interface ConfirmScreenSnapshot {
  url: string;
  /** 入札額の入力欄の数。0 なら確認画面に着いている(地雷12c) */
  priceInputCount: number;
  /** 現行の bidSubmitButton セレクタに当たった数 */
  submitSelectorHits: number;
  /** 画面に見えているボタン系要素のラベル */
  labels: string[];
  /** MAX_LABELS で切り落としたか */
  truncated: boolean;
}

/** 重複を潰し、長さと件数で切る。切ったかどうかも返す */
export function normalizeLabels(raw: string[]): { labels: string[]; truncated: boolean } {
  const seen = new Set<string>();
  for (const r of raw) {
    const t = r.replace(/\s+/g, " ").trim();
    if (!t) continue;
    seen.add(t.length > MAX_LABEL_CHARS ? `${t.slice(0, MAX_LABEL_CHARS)}…` : t);
  }
  const all = [...seen];
  return { labels: all.slice(0, MAX_LABELS), truncated: all.length > MAX_LABELS };
}

/** 人が1行で読める形にする(失敗通知と BidAttempt.detail に載せる) */
export function formatConfirmScreenSnapshot(s: ConfirmScreenSnapshot): string {
  const labels =
    s.labels.length === 0
      ? "(可視ボタン0件)"
      : s.labels.map((l) => JSON.stringify(l)).join(" / ") + (s.truncated ? " …" : "");
  return (
    `[確認画面の実測] 入力欄=${s.priceInputCount}件` +
    ` / 現行セレクタのヒット=${s.submitSelectorHits}件` +
    ` / 可視ボタン=${labels}`
  );
}

/**
 * ガードが落ちた画面を1往復で計測する。
 *
 * ⚠️ 失敗しても呼び出し側を壊さない。ここで例外を投げると、
 * 「押さずに止めた」という正しい結末が「計測で落ちた」に化ける。
 */
export async function captureConfirmScreen(page: Page): Promise<string> {
  try {
    const timer = new Promise<null>((resolve) =>
      setTimeout(() => resolve(null), CAPTURE_TIMEOUT_MS),
    );
    const work = (async () => {
      // ⚠️ worker の tsconfig に DOM の型は入っていない(Node 向け)。
      // ブラウザ側で動くこの関数のためだけに lib を足すと、fetch など
      // Node 側の型まで DOM 版に差し替わるので、必要な形だけここで書く。
      interface ClickableLike {
        getClientRects(): { length: number };
        textContent: string | null;
        value?: unknown;
      }
      interface DocumentLike {
        querySelectorAll(sel: string): ArrayLike<ClickableLike>;
      }
      const raw = await page.evaluate(() => {
        const doc = (globalThis as unknown as { document: DocumentLike }).document;
        const out: string[] = [];
        const nodes = Array.from(
          doc.querySelectorAll("button, input[type=submit], input[type=button], [role=button]"),
        );
        for (const el of nodes) {
          // 非表示の要素は押せないので候補から外す。
          // 裏のモーダルに隠れているだけの要素は矩形を持つので残る
          // (それこそが「裏の入札するボタン」で、見えている必要がある)。
          if (el.getClientRects().length === 0) continue;
          const value = typeof el.value === "string" ? el.value : "";
          const text = `${el.textContent ?? ""} ${value}`;
          if (text.trim()) out.push(text);
        }
        return out;
      });
      const priceInputCount = await page.locator(selectors.priceInput).count();
      const submitSelectorHits = await page.locator(selectors.bidSubmitButton).count();
      const { labels, truncated } = normalizeLabels(raw);
      return formatConfirmScreenSnapshot({
        url: page.url(),
        priceInputCount,
        submitSelectorHits,
        labels,
        truncated,
      });
    })();
    return (await Promise.race([work, timer])) ?? "[確認画面の実測] 計測がタイムアウトしました";
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return `[確認画面の実測] 計測に失敗: ${msg}`;
  }
}

// =============================================================
// 入札ボタン(bidButton)が掴めなかったときの計測。
//
// なぜ要るか: 2026-09-02 の実入札(k1242598835)は
// `waiting for locator('role=button[name="入札する"]')` の Timeout 1行だけを
// 残して失敗した。この1行からは
//   ① 文言か要素の種類が変わった(新UI→旧UIの <a> など)
//   ② CSR が終わっておらず DOM がまだ空
//   ③ そもそも商品ページに居ない(ログイン壁・エラーページ・確認画面)
// のどれなのかが分からない。切り分けにはオークションをもう1件使うしかなく、
// これは確認画面で 2026-08-28 に起きたのと同じ失い方(diagnose の理由)。
//
// ⚠️ `<a>` も数えること。旧UIの入札の入口はボタンではなくリンク
// (`/jp/show/bid`)で、role=button のセレクタからは永久に見えない(地雷2/5)。
// ⚠️ 残すのはラベル・件数・パス名だけ。Cookie・アカウント情報は触らない(設計 §8)。

export interface BidEntrySnapshot {
  url: string;
  /** ページタイトル。エラーページ・ログイン画面はここに出る */
  title: string;
  /** 現行の bidButton セレクタに当たった数 */
  bidSelectorHits: number;
  /** loginLink の数。商品ページでは 0 でも未ログインとは限らない(sessionVerdict.ts) */
  loginLinkHits: number;
  /** クリック要素の総数。5未満なら描画が終わっていない疑い(pageReady.ts) */
  clickable: number;
  /** 「入札」を含む可視要素。`<tag パス> ラベル` の形 */
  bidLikeLabels: string[];
  truncated: boolean;
}

/** 人が1行で読める形にする(失敗通知と BidAttempt.detail に載せる) */
export function formatBidEntrySnapshot(s: BidEntrySnapshot): string {
  const labels =
    s.bidLikeLabels.length === 0
      ? "(0件)"
      : s.bidLikeLabels.map((l) => JSON.stringify(l)).join(" / ") + (s.truncated ? " …" : "");
  return (
    `[入札ボタンの実測] URL=${s.url}` +
    ` / タイトル=${JSON.stringify(s.title)}` +
    ` / 現行セレクタのヒット=${s.bidSelectorHits}件` +
    ` / ログインリンク=${s.loginLinkHits}件` +
    ` / クリック要素=${s.clickable}個` +
    ` / 「入札」を含む可視要素=${labels}`
  );
}

/**
 * 入札ボタンを掴めなかった画面を1往復で計測する。
 *
 * ⚠️ 失敗しても呼び出し側を壊さない。ここで例外を投げると、
 * 「入札ボタンが見つからなかった」という結末が「計測で落ちた」に化ける。
 */
export async function captureBidEntry(page: Page): Promise<string> {
  try {
    const timer = new Promise<null>((resolve) =>
      setTimeout(() => resolve(null), CAPTURE_TIMEOUT_MS),
    );
    const work = (async () => {
      interface ClickableLike {
        getClientRects(): { length: number };
        textContent: string | null;
        tagName?: unknown;
        pathname?: unknown;
        value?: unknown;
      }
      interface DocumentLike {
        querySelectorAll(sel: string): ArrayLike<ClickableLike>;
      }
      const raw = await page
        .evaluate(() => {
          const doc = (globalThis as unknown as { document: DocumentLike }).document;
          const out: string[] = [];
          const nodes = Array.from(
            doc.querySelectorAll(
              "button, a, input[type=submit], input[type=button], [role=button]",
            ),
          );
          for (const el of nodes) {
            if (el.getClientRects().length === 0) continue;
            const value = typeof el.value === "string" ? el.value : "";
            const text = `${el.textContent ?? ""} ${value}`;
            // 「入札」を含むものだけ。全部出すと通知が読めなくなる
            if (!text.includes("入札")) continue;
            const tag = typeof el.tagName === "string" ? el.tagName.toLowerCase() : "?";
            // 旧UIの入口はリンク。`/jp/show/bid` と `/jp/show/bid_hist` の
            // 区別が付くようにパス名だけ載せる(地雷2)
            const path = typeof el.pathname === "string" ? el.pathname : "";
            out.push(`<${tag}${path ? ` ${path}` : ""}> ${text}`);
          }
          return out;
        })
        .catch(() => [] as string[]);
      const bidSelectorHits = await page.locator(selectors.bidButton).count().catch(() => -1);
      const loginLinkHits = await page.locator(selectors.loginLink).count().catch(() => -1);
      const clickable = await page
        .locator("button, input[type=submit], input[type=button], a")
        .count()
        .catch(() => -1);
      const title = await Promise.resolve()
        .then(() => page.title())
        .catch(() => "");
      const { labels, truncated } = normalizeLabels(raw);
      return formatBidEntrySnapshot({
        url: page.url(),
        title,
        bidSelectorHits,
        loginLinkHits,
        clickable,
        bidLikeLabels: labels,
        truncated,
      });
    })();
    return (await Promise.race([work, timer])) ?? "[入札ボタンの実測] 計測がタイムアウトしました";
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return `[入札ボタンの実測] 計測に失敗: ${msg}`;
  }
}
