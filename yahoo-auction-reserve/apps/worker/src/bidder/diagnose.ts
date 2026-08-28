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
