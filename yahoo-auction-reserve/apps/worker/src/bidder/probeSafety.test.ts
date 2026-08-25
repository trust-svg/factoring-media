import assert from "node:assert/strict";
import { test } from "node:test";
import { confirmClickVerdict, submitTargetVerdict } from "./probeSafety";

const V = (label: string, submitKeys: string[] = [], confirmKey = "btn|||確認") =>
  confirmClickVerdict({ confirmKey, submitKeys, label });

test("確認ボタンらしいラベルなら押してよい", () => {
  const v = V("入札内容を確認する");
  assert.equal(v.safe, true);
});

test("確定ボタン候補と同一要素なら押さない", () => {
  const v = V("入札内容を確認する", ["btn|||確認"]);
  assert.equal(v.safe, false);
  assert.match(v.reason, /同一の要素/);
});

test("確定ボタン候補が別要素なら押してよい", () => {
  const v = V("入札内容を確認する", ["other|||入札する"]);
  assert.equal(v.safe, true);
});

test("ラベルに「確認」が無いものは押さない(未検証プレースホルダ対策)", () => {
  const v = V("次へ");
  assert.equal(v.safe, false);
  assert.match(v.reason, /確認/);
});

test("空ラベルは押さない", () => {
  assert.equal(V("").safe, false);
});

test("「確認して入札する」型の1段確定ボタンは押さない", () => {
  // 「確認」を含むので条件2は通ってしまう。ここで落ちないと実入札が飛ぶ
  const v = V("入札内容を確認して入札する");
  assert.equal(v.safe, false);
  assert.match(v.reason, /入札する/);
});

test("素の「入札する」も押さない", () => {
  assert.equal(V("入札する").safe, false);
});

test("判定は安全側に非対称 — 迷う入力は全部 unsafe になる", () => {
  for (const label of ["", "OK", "送信", "入札", "確定"]) {
    assert.equal(V(label).safe, false, `${label} は押してはいけない`);
  }
});

const S = (sameAsBidButton: boolean, found = true, navigated = false) =>
  submitTargetVerdict({ sameAsBidButton, found, navigated });

test("確定ボタンが別要素として見つかっていれば押してよい", () => {
  assert.equal(S(false).safe, true);
  assert.equal(S(false).reason, "");
});

test("最初の入札ボタンと同一要素なら押さない(確認画面に着いていない)", () => {
  const v = S(true);
  assert.equal(v.safe, false);
  assert.match(v.reason, /同一要素/);
});

test("確定ボタンが見つからないなら押さない", () => {
  const v = S(false, false);
  assert.equal(v.safe, false);
  assert.match(v.reason, /見つからない/);
});

test("見つからない判定は同一要素判定より先(理由が上流原因になる)", () => {
  assert.match(S(true, false).reason, /見つからない/);
});

test("遷移していれば同一要素になりようがないので通す", () => {
  // 遷移をまたぐと要素の同一性比較は必ず失敗する。呼び出し側は
  // 比較不能を true(止める)で渡すので、順序が逆だと正常な入札が全部止まる
  assert.equal(S(true, true, true).safe, true);
});

test("遷移していなければ同一要素判定が効く", () => {
  assert.equal(S(true, true, false).safe, false);
});

test("遷移していても確定ボタンが無ければ押さない", () => {
  assert.equal(S(false, false, true).safe, false);
});
