import { test } from "node:test";
import assert from "node:assert/strict";
import { chromium, type Page } from "playwright";
import { selectors } from "../../src/bidder/selectors";

// 入札フォームを開く入口ボタンのセレクタ。
//
// 2026-09-04 の d1242748141 は、`role=button[name="入札する"]`(完全一致)が
// **1件も当たらないまま15秒 Timeout ×2 で終わった**。実ページを計測したら
// ボタンの文言が「値段を上げて入札」だった(自分がその商品に入札済みだと
// 変わる。selectors.ts の地雷15)。そこで2つの文言を1本の正規表現で拾う
// 形にしたが、**その形は実ページに当てていない**。
// ここでは実測した文言を再現した HTML に当てて、少なくとも
// 「書き方として両方に当たり、余計なものは拾わない」ことを固定する。
//
// 被害は非対称:
//   狭すぎ → 入口を掴めず入札が一度も成立しない(2026-09-04 に実際に起きた)
//   緩すぎ → 「入札履歴」等を押して、押したつもりでフォームが開かない(地雷2)
//
// ⚠️ 実ブラウザを起動するので `npm test` の glob から外してある
// (`npm run test:browser`)。Claude Code の sandbox 内では Chromium が
// 起動できない(mach port の permission denied)ので、sandbox 外か
// worker コンテナ内で実行すること。

/** 実測した入口ボタンの文言(この2つには必ず当たること) */
const REAL_ENTRY_LABELS = [
  // 2026-09-02 23:13 の実ページ。可視の <button> が2件
  "入札する",
  // 2026-09-04 の実入札(d1242748141)の計測。自分が入札済みの商品
  "値段を上げて入札",
];

/**
 * 同じページに居て、掴んではいけないもの。
 * ⚠️ 「入札する」「値段を上げて入札」以外は **実測していない文言** で、
 * ヤフオクにこの通り出る保証は無い。正規表現を緩めたときに何が巻き込まれるかを
 * 見るための当て馬として置いている(「入札」だけの部分一致に戻すと全部当たる)。
 */
const MUST_NOT_MATCH = [
  "まとめて入札する", // 複数商品を一度に。押すと別の商品まで対象になる
  "入札履歴", // 地雷2: 部分一致にすると先に当たる
  "自動入札の設定",
  "入札をキャンセル",
  "ウォッチリストに追加",
  // 確認画面の確定ボタン。入口として掴むと手順が1つ飛ぶ(2026-08-28 実測の文言)
  "上記のガイドライン等、情報提供に同意して 入札する",
];

const SHAPES: Record<string, (label: string) => string> = {
  button: (t) => `<button>${t}</button>`,
  "input[type=submit]": (t) => `<input type="submit" value="${t}">`,
  "div[role=button]": (t) => `<div role="button" tabindex="0">${t}</div>`,
};

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

function html(render: (t: string) => string, labels: string[]): string {
  return `<!doctype html><meta charset="utf-8"><body>${labels.map(render).join("\n")}</body>`;
}

for (const [shape, render] of Object.entries(SHAPES)) {
  for (const label of REAL_ENTRY_LABELS) {
    test(`${shape} の入口ボタンに当たる: ${label}`, async () => {
      await withPage(html(render, [label, ...MUST_NOT_MATCH]), async (page) => {
        const hits = await page.locator(selectors.bidButton).count();
        assert.equal(hits, 1, `ヒット数が1件でない(${hits}件)`);
      });
    });
  }

  test(`${shape} で紛らわしいボタンだけなら0件`, async () => {
    // ⚠️ ここが1件以上になる書き方は、押しても入札フォームが開かない。
    // 開かないまま入力欄を探して15秒待ち、Timeout で終わる。
    await withPage(html(render, MUST_NOT_MATCH), async (page) => {
      const loc = page.locator(selectors.bidButton);
      const hits = await loc.count();
      assert.equal(hits, 0, `掴んではいけないものに当たった: ${await loc.allTextContents()}`);
    });
  });
}

test("実ページと同じく「入札する」が2件あれば2件とも当たる", async () => {
  // 2026-09-02 実測: 可視の「入札する」<button> は2件。first() で先頭を押す。
  await withPage(html(SHAPES.button, ["入札する", "入札する", ...MUST_NOT_MATCH]), async (page) => {
    assert.equal(await page.locator(selectors.bidButton).count(), 2);
  });
});

test("入札済みの商品ページ(入口が1つだけ文言違い)でも掴める", async () => {
  await withPage(
    html(SHAPES.button, ["値段を上げて入札", "値段を上げて入札", ...MUST_NOT_MATCH]),
    async (page) => {
      assert.equal(await page.locator(selectors.bidButton).count(), 2);
    },
  );
});
