import assert from "node:assert/strict";
import { test } from "node:test";
import { confirmClickVerdict } from "./probeSafety";

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
