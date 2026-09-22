import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import { isRebookableReservation, sessionVerificationKind } from "./labels";

const t = "2026-08-25T12:00:00+09:00";

describe("sessionVerificationKind", () => {
  it("確認できていれば VERIFIED", () => {
    assert.equal(sessionVerificationKind(t, t), "VERIFIED");
  });

  it("一度も試していなければ PENDING(登録直後)", () => {
    assert.equal(sessionVerificationKind(null, null), "PENDING");
  });

  it("試したのに確認できていなければ INCONCLUSIVE", () => {
    // PENDING と同じ表示にすると、判定機構が壊れている状態が
    // 「まだ順番が来ていないだけ」に見えて放置される
    const kind = sessionVerificationKind(null, t);
    assert.equal(kind, "INCONCLUSIVE");
    assert.notEqual(kind, "PENDING");
  });

  it("確認できていれば、その後の試行時刻に関わらず VERIFIED", () => {
    assert.equal(sessionVerificationKind(t, null), "VERIFIED");
  });

  it("undefined は null と同じに扱う(select 漏れで壊れない)", () => {
    assert.equal(sessionVerificationKind(undefined, undefined), "PENDING");
  });
});

describe("isRebookableReservation", () => {
  it("キャンセル・失敗・落札ならず・スキップ・テスト実行は予約し直せる", () => {
    for (const s of ["CANCELLED", "FAILED", "LOST", "EXPIRED", "DRY_RUN"]) {
      assert.equal(isRebookableReservation(s), true, s);
    }
  });

  it("動いている予約は予約し直せない(二重予約になる)", () => {
    for (const s of ["SCHEDULED", "MONITORING", "BIDDING"]) {
      assert.equal(isRebookableReservation(s), false, s);
    }
  });

  it("WON は「終わった予約」だが予約し直せない", () => {
    // ダッシュボードの「結果」タブ(DONE)と同じ一覧にしてはいけない。
    // 落札済みの商品を予約し直すことはできない。
    assert.equal(isRebookableReservation("WON"), false);
  });

  it("知らない値は「動いている」側に倒す", () => {
    // enum が増えた日に、知らない状態を勝手に「終わっている」と読んで
    // 二重予約させない
    assert.equal(isRebookableReservation("NEW_STATUS"), false);
  });
});
