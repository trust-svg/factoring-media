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

// 2026-08-28 実測の確定ボタンの表示テキスト。
const SUBMIT_LABEL = "上記のガイドライン等、情報提供に同意して 入札する";

const S = (
  sameAsBidButton: boolean,
  found = true,
  navigated = false,
  label = SUBMIT_LABEL,
  formStillOpen = false,
) => submitTargetVerdict({ sameAsBidButton, found, navigated, label, formStillOpen });

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

test("入札額の入力欄が残っていれば押さない(確認画面に進んでいない)", () => {
  const v = S(false, true, false, SUBMIT_LABEL, true);
  assert.equal(v.safe, false);
  assert.match(v.reason, /入力欄/);
});

// ⚠️ 商品ページには「入札する」ボタンが2つある(2026-08-28 実測)。
// 同一要素判定は最初に押した1つとしか比較しないので、もう片方を掴むと
// sameAsBidButton=false のまま通り抜ける。ラベルで落とす。
test("ラベルが「入札する」ちょうどなら押さない — 裏に残る商品ページのボタン", () => {
  const v = S(false, true, false, "入札する");
  assert.equal(v.safe, false);
  assert.match(v.reason, /商品ページ側/);
});

test("前後の空白を削っても「入札する」ちょうどなら押さない", () => {
  assert.equal(S(false, true, false, " 入札する \n").safe, false);
});

test("遷移していても、ラベルが商品ページ側のボタンなら押さない", () => {
  // navigated=true は同一要素判定を飛ばす逃げ道。ラベル判定はその前に置く。
  assert.equal(S(false, true, true, "入札する").safe, false);
});

test("文言が変わって「入札」を含まなくなったら押さない", () => {
  const v = S(false, true, false, "同意して落札する");
  assert.equal(v.safe, false);
  assert.match(v.reason, /入札/);
});

// ⚠️ 自分がその商品に入札済みだと、商品ページ側のボタンの文言が
// 「値段を上げて入札」に変わる(2026-09-04 実測・selectors.ts の地雷15)。
// 「入札する」だけを弾いていると、入札済みの商品ではこのボタンが
// 確定ボタンとしてこのガードを素通りする = 入札していないのに SUCCESS。
test("ラベルが「値段を上げて入札」ちょうどなら押さない — 入札済み商品の裏のボタン", () => {
  const v = S(false, true, false, "値段を上げて入札");
  assert.equal(v.safe, false);
  assert.match(v.reason, /商品ページ側/);
});

test("「値段を上げて入札」も遷移後・空白付きで弾く", () => {
  assert.equal(S(false, true, true, "値段を上げて入札").safe, false);
  assert.equal(S(false, true, false, " 値段を上げて入札 \n").safe, false);
});

// 入口が「値段を上げて入札」に変わる商品では、確定側も
// 「…同意…値段を上げて入札」になりうる(未実測)。「入札する」で判定していると
// 正しく掴んでいるのにここで落ちて、入札が一度も成立しない。
test("確定ボタンが「入札する」以外の入札文言でも、同意の語があれば通る", () => {
  assert.equal(
    S(false, true, false, "上記のガイドライン等、情報提供に同意して 値段を上げて入札").safe,
    true,
  );
});

test("実測した確定ボタンのラベルは通る", () => {
  // ここが false になったら、本番で入札が一度も成立しなくなる
  assert.equal(S(false, true, false, SUBMIT_LABEL).safe, true);
});

test("入力欄の判定は見つからない判定より後・ラベル判定より先", () => {
  // 上流原因(そもそも見つかっていない)を先に出す
  assert.match(S(false, false, false, "入札する", true).reason, /見つからない/);
  // 入力欄が残っているのは「画面が進んでいない」= ラベルの話より上流
  assert.match(S(false, true, false, "入札する", true).reason, /入力欄/);
});
