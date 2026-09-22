import { test } from "node:test";
import assert from "node:assert/strict";
import {
  SNIPE_SECONDS_MIN,
  SNIPE_SECONDS_MAX,
  SNIPE_SECONDS_DEFAULT,
  MONITOR_WARMUP_SECONDS,
  monitorLeadSeconds,
  editDeadlineSeconds,
} from "./constants";

// 指定できる実行秒数を端から端まで舐める。境界だけ見ていると、
// 「90 までは正しく動くが 91 から黙って壊れる」型の欠陥を取り逃す。
const allSnipeSeconds = Array.from(
  { length: SNIPE_SECONDS_MAX - SNIPE_SECONDS_MIN + 1 },
  (_, i) => SNIPE_SECONDS_MIN + i,
);

test("SNIPE_SECONDS_DEFAULT は指定可能な範囲に入っている", () => {
  assert.ok(SNIPE_SECONDS_DEFAULT >= SNIPE_SECONDS_MIN);
  assert.ok(SNIPE_SECONDS_DEFAULT <= SNIPE_SECONDS_MAX);
});

test("monitor の起動は必ず入札予定時刻より前になる(全ての実行秒数で)", () => {
  // これが破れると sleepUntil が過去時刻で即座に返り、設定を無視して
  // monitor の起動時刻に入札してしまう。エラーは一切出ない。
  for (const s of allSnipeSeconds) {
    assert.ok(
      monitorLeadSeconds(s) > s,
      `snipeSecondsBefore=${s} で monitor が入札予定時刻より後に起動する ` +
        `(lead=${monitorLeadSeconds(s)})`,
    );
  }
});

test("monitor の起動はウォームアップ分だけ手前にある", () => {
  for (const s of allSnipeSeconds) {
    assert.equal(monitorLeadSeconds(s) - s, MONITOR_WARMUP_SECONDS);
  }
});

test("登録・変更の締切は monitor の起動より前にある(全ての実行秒数で)", () => {
  // 締切が monitor の起動より後だと、既に走り出したジョブの内容を
  // 変更できてしまい、画面上は変更成功なのに入札は旧設定で実行される。
  for (const s of allSnipeSeconds) {
    assert.ok(
      editDeadlineSeconds(s) > monitorLeadSeconds(s),
      `snipeSecondsBefore=${s} で締切が monitor 起動より後になる`,
    );
  }
});

test("実行秒数を長くすると締切も必ず早まる(単調性)", () => {
  for (let i = 1; i < allSnipeSeconds.length; i++) {
    const prev = allSnipeSeconds[i - 1]!;
    const cur = allSnipeSeconds[i]!;
    assert.ok(editDeadlineSeconds(cur) > editDeadlineSeconds(prev));
  }
});
