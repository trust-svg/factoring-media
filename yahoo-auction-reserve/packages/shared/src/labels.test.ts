import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import { sessionVerificationKind } from "./labels";

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
