import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { NOTIFICATION_CATEGORY, type NotificationType } from "./types";
import { RESERVATION_STATUS_LABEL, ATTEMPT_OUTCOME_LABEL } from "./labels";

describe("通知の系統", () => {
  // ユーザー設定で切れるのは RESULT / ERROR だけ(apps/worker/src/notify.ts)。
  // テスト実行の結果をそのどちらかに入れると、結果通知を切っている人が
  // テスト実行したとき **何も届かないまま終わる** = 予定時刻に動かなかった
  // 場合と区別が付かない。テスト実行の目的そのものが消える。
  it("テスト実行の結果は、ユーザー設定で切れる系統に入れない", () => {
    const category = NOTIFICATION_CATEGORY.DRY_RUN;
    assert.equal(category, "TEST");
    assert.notEqual(category, "RESULT");
    assert.notEqual(category, "ERROR");
  });

  // 高値更新の通知は「結果の報告」ではなく「まだ間に合ううちに増額しますか」
  // の問い合わせ。RESULT / ERROR に入れると通知設定で切れてしまい、切っている人は
  // **追加入札できたことを知らないまま負ける**(切った人が想定しているのは
  // 終わったあとの報告であって、行動の機会ではない)。
  it("高値更新の通知は、ユーザー設定で切れる系統に入れない", () => {
    const category = NOTIFICATION_CATEGORY.OUTBID;
    assert.equal(category, "ACTION");
    assert.notEqual(category, "RESULT");
    assert.notEqual(category, "ERROR");
  });

  it("全ての通知種別に系統が割り当てられている", () => {
    const types: NotificationType[] = [
      "WON", "LOST", "AUTO_RAISED", "GROUP_CANCELLED",
      "FAILED", "EXPIRED", "SESSION_EXPIRED", "RAISE_DECLINED",
      "REMINDER", "APPROVAL_REQUEST", "DAILY_SUMMARY", "DRY_RUN",
      "ALREADY_HIGHEST", "OUTBID",
    ];
    for (const t of types) {
      assert.ok(NOTIFICATION_CATEGORY[t], `${t} に系統が無い`);
    }
    assert.equal(Object.keys(NOTIFICATION_CATEGORY).length, types.length);
  });
});

describe("テスト実行のラベル", () => {
  // 「入札していない」ことが表示から読み取れないと、落札できなかったのか
  // そもそも入札していないのかが分からない。
  it("予約の状態ラベルに「入札していません」と書いてある", () => {
    assert.equal(RESERVATION_STATUS_LABEL.DRY_RUN, "テスト実行(入札していません)");
  });

  it("試行結果のラベルに「確定は押していない」と書いてある", () => {
    assert.ok(ATTEMPT_OUTCOME_LABEL.DRY_RUN.includes("確定は押していない"));
  });
});
