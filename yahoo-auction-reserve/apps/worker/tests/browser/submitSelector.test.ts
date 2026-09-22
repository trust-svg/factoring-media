import { test } from "node:test";
import assert from "node:assert/strict";
import { chromium, type Page } from "playwright";
import { selectors } from "../../src/bidder/selectors";
import { submitTargetVerdict } from "../../src/bidder/probeSafety";

// 確定ボタンのセレクタは、当てずっぽうで直すと被害が非対称になる。
// 緩すぎると確認画面の裏に残っている商品ページの「入札する」を押して
// **入札していないのに SUCCESS** を返し(地雷12b)、狭すぎると入札が
// 一度も成立しない(2026-08-28 の DRY_RUN は2回とも狭すぎで失敗した)。
//
// ヤフオクに触らずに固定できるよう、実測したラベルを再現した HTML に
// 当てる。ラベルの出典は BidAttempt の [確認画面の実測] と Stage 2 レポート。
// 文言は商品によって変わるので **両方に当たること** が要件。
//
// ⚠️ このファイルだけ実ブラウザを起動するので `npm test` の glob から
// 外してある(`npm run test:browser` で走る)。Claude Code の sandbox 内では
// Chromium が起動できない(mach port の permission denied)ため、
// sandbox 外か worker コンテナ内で実行すること。

/** 確認画面が出ている間も DOM に残る、裏の商品ページ側のボタン(地雷12b) */
const BACKGROUND_BUTTONS = [
  "入札する",
  "入札する",
  "すべてのカテゴリ",
  "検索する",
  "配送方法一覧",
  "落札率が高い",
  "詳細",
  "その他の情報",
  "故障時も安心！ PayPayほけん・あんしん修理",
  "もっと見る",
  "TOP",
  "商品説明",
];

/** 実測できている確定ボタンの文言 */
const REAL_SUBMIT_LABELS = [
  "上記に同意のうえ入札する",
  "上記のガイドライン等、情報提供に同意して 入札する",
];

// ボタンがどの要素で描かれているかは未実測なので、ありうる3形すべてで通す。
// `<input type="submit">` は textContent を持たないため、`has-text` 系の
// セレクタはここで落ちる(実際 2026-08-28 の候補選びで落ちた)。
const SHAPES: Record<string, (label: string) => string> = {
  button: (t) => `<button>${t}</button>`,
  "input[type=submit]": (t) => `<input type="submit" value="${t}">`,
  "div[role=button]": (t) => `<div role="button" tabindex="0">${t}</div>`,
};

function html(render: (t: string) => string, submitLabel: string | null): string {
  const buttons = [...BACKGROUND_BUTTONS, ...(submitLabel ? [submitLabel] : [])];
  return `<!doctype html><meta charset="utf-8"><body>${buttons.map(render).join("\n")}</body>`;
}

async function withPage<T>(content: string, fn: (page: Page) => Promise<T>): Promise<T> {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    await page.setContent(content);
    return await fn(page);
  } finally {
    await browser.close();
  }
}

for (const [shape, render] of Object.entries(SHAPES)) {
  for (const label of REAL_SUBMIT_LABELS) {
    test(`${shape} の確定ボタンにちょうど1件当たる: ${label}`, async () => {
      await withPage(html(render, label), async (page) => {
        const target = page.locator(selectors.bidSubmitButton);
        const hits = await target.count();
        assert.equal(hits, 1, `ヒット数が1件でない(${hits}件)`);

        // 押してよいと判定されるところまで確かめる。セレクタが当たっても
        // ガードで落ちるなら入札は成立しない。
        const text = await target.first().evaluate((el) => {
          const node = el as unknown as { value?: unknown; textContent: string | null };
          return typeof node.value === "string" && node.value ? node.value : (node.textContent ?? "");
        });
        const verdict = submitTargetVerdict({
          found: true,
          navigated: false,
          sameAsBidButton: false,
          formStillOpen: false,
          label: text,
        });
        assert.ok(verdict.safe, `ガードで落ちた: ${verdict.reason}`);
      });
    });
  }

  test(`${shape} で確定ボタンが無ければ0件(=確認画面に着いていない)`, async () => {
    // ⚠️ ここが1件以上になるセレクタは、裏の「入札する」を掴んでいる。
    // その状態で押すと入札は成立しないのに SUCCESS が返る。
    await withPage(html(render, null), async (page) => {
      assert.equal(await page.locator(selectors.bidSubmitButton).count(), 0);
    });
  });
}
