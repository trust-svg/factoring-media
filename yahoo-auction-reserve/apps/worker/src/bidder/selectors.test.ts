import { test } from "node:test";
import assert from "node:assert/strict";
import { selectors } from "./selectors";

// 実ブラウザを使う本番の検証は tests/browser/submitSelector.test.ts。
// ここはブラウザ無しで守れる不変条件だけを置く(sandbox 内の `npm test` でも走る)。

test("確定ボタンのセレクタは「同意」を要求している", () => {
  // 確認画面の裏に残る商品ページのボタンは **ちょうど**「入札する」。
  // 「同意」が抜けた瞬間、押しても入札が成立しない裏のボタンに当たる
  // ようになり、しかも SUCCESS が返る(地雷12b)。
  assert.match(selectors.bidSubmitButton, /同意/);
});

test("確定ボタンのセレクタは textContent 依存の has-text を使っていない", () => {
  // `<input type="submit">` は textContent を持たないので has-text では
  // 0件になる。確認画面のボタンがどの要素かは未実測なので role で拾う。
  assert.ok(
    !selectors.bidSubmitButton.includes("has-text"),
    "has-text は input[type=submit] に当たらない",
  );
});

test("確定ボタンと入札ボタンのセレクタは別物", () => {
  // 同じになると「別要素であること」を要求するガードが常に落ちる。
  assert.notEqual(selectors.bidSubmitButton, selectors.bidButton);
});
