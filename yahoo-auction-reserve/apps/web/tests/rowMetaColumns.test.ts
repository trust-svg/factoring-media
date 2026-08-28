import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// PC 幅では .row-meta が display:contents で親の固定列グリッドに流し込まれる。
// つまり **row-meta の子要素の数と grid-template-columns の列数が一致していないと
// 全行の桁がずれる**。しかも即決価格のように「ある行と無い行がある」項目を
// 条件付きで描くと、即決ありの行だけ以降の列が1つずれる = 一覧で価格と
// 上限額を見比べられなくなる。CSS 側だけ直すことも TSX 側だけ直すことも
// できてしまうので、両方を突き合わせてここで固定する。

const WEB = join(__dirname, "..");
const LIST = readFileSync(join(WEB, "app/dashboard/ReservationList.tsx"), "utf8");
const CSS = readFileSync(join(WEB, "app/globals.css"), "utf8");

/** .snipe-row 直下の子(row-meta の中身は display:contents で展開される) */
const ROW_CHILDREN = ["row-thumb", "row-title", "row-meta", "row-clock", "row-end", "row-note"];
/** row-meta の中身。ここに足したら CSS の列も増やすこと */
const META_CHILDREN = ["m-price", "m-arrow", "m-cap", "m-bin", "m-ext", "m-timing"];

function pcColumnCount(): number {
  // ⚠️ 最初に見つかる .snipe-row はモバイル用(grid-template-areas 方式)。
  // 列を持つのは PC 用の上書きだけで、それは areas を none に潰してから
  // 列を宣言している。素直に先頭マッチを取るとモバイルの4列を数えて
  // 「ずれている」と誤検知する。
  const m = CSS.match(
    /\.snipe-row\s*\{[^}]*grid-template-areas:\s*none;[^}]*grid-template-columns:\s*([^;]+);/,
  );
  assert.ok(m, "PC 用の .snipe-row grid-template-columns が見つからない");
  // minmax(0, 1fr) は 1 列。空白で割る前に括弧の中身を潰す
  return m[1].replace(/\([^)]*\)/g, "()").trim().split(/\s+/).length;
}

test("row-meta の子の数と PC グリッドの列数が一致している", () => {
  // 列 = thumb + title + row-meta の中身 + end + clock
  // (row-note は PC では display:none なので列を持たない)
  const expected = 2 + META_CHILDREN.length + 2;
  assert.equal(
    pcColumnCount(),
    expected,
    `列数がずれている。row-meta に要素を足したら globals.css の ` +
      `grid-template-columns にも列を足すこと`,
  );
});

test("row-meta の子はすべて実装されており、余分な子がない", () => {
  const used = [...LIST.matchAll(/className=\{?[`"]([^`"]*m-[a-z]+)/g)]
    .flatMap((m) => m[1].split(/\s+/))
    .filter((c) => c.startsWith("m-"));
  for (const c of META_CHILDREN) {
    assert.ok(used.includes(c), `${c} が ReservationList.tsx に無い`);
  }
  for (const c of new Set(used)) {
    assert.ok(META_CHILDREN.includes(c), `未知の列 ${c} が増えている(CSS の列数も要確認)`);
  }
});

test("即決価格の m-bin は、即決価格が無い行でも描かれる", () => {
  // 「即決あり/なしで要素数が変わる」= 行ごとに列がずれる。
  // 早期 return は空の span を返すこと(null を返すと列が消える)。
  const fn = LIST.match(/function BuyNow\([\s\S]*?\n\}/);
  assert.ok(fn, "BuyNow コンポーネントが見つからない");
  assert.ok(
    /buyNowPrice == null\)\s*return\s*<span className="m-bin"/.test(fn[0]),
    "即決価格が null のとき、m-bin の span を描かずに返している(列がずれる)",
  );
  assert.ok(!/return null/.test(fn[0]), "BuyNow が null を返している(列がずれる)");
});

test("上限額が即決価格以上のときの警告が PC でも見える場所に出ている", () => {
  // row-note は PC 幅で display:none。警告をそこだけに置くと PC で消える。
  assert.ok(/\.row-note\s*\{\s*display:\s*none/.test(CSS), "前提(row-note が PC で非表示)が変わった");
  assert.ok(/m-bin\$\{over \? " over" : ""\}/.test(LIST), "m-bin に警告クラスが付いていない");
  assert.ok(/\.m-bin\.over\s*\{/.test(CSS), ".m-bin.over のスタイルが無い");
});
