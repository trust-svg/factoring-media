import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { cancelVerdict } from "./cancel";

describe("入札予約のキャンセル可否", () => {
  it("まだ何も始まっていない(SCHEDULED)なら通す", () => {
    const v = cancelVerdict({ status: "SCHEDULED", hasSuccessfulBid: false });
    assert.equal(v.ok, true);
    assert.equal(v.refusal, undefined);
  });

  it("監視中(MONITORING)でも入札前なら通す", () => {
    const v = cancelVerdict({ status: "MONITORING", hasSuccessfulBid: false });
    assert.equal(v.ok, true);
  });

  // ⚠️ ここが status だけで判定してはいけない理由。自動延長の再スナイプでは
  // 入札に成功したあと status が MONITORING に戻る。
  it("MONITORING でも入札済みなら断る(自動延長で status が戻る回)", () => {
    const v = cancelVerdict({ status: "MONITORING", hasSuccessfulBid: true });
    assert.equal(v.ok, false);
    assert.equal(v.refusal, "ALREADY_BID");
  });

  it("入札処理の実行中(BIDDING)は、成功記録が無くても断る", () => {
    const v = cancelVerdict({ status: "BIDDING", hasSuccessfulBid: false });
    assert.equal(v.ok, false);
    assert.equal(v.refusal, "IN_FLIGHT");
  });

  it("入札済みの判定は BIDDING より先に効く", () => {
    const v = cancelVerdict({ status: "BIDDING", hasSuccessfulBid: true });
    assert.equal(v.refusal, "ALREADY_BID");
  });

  for (const status of ["WON", "LOST", "FAILED", "CANCELLED", "EXPIRED", "DRY_RUN"]) {
    it(`決着済み(${status})は断る`, () => {
      const v = cancelVerdict({ status, hasSuccessfulBid: false });
      assert.equal(v.ok, false);
      assert.equal(v.refusal, "FINISHED");
    });
  }

  it("断るときは必ず理由の文言が入る(空文字のまま UI に出さない)", () => {
    for (const row of [
      { status: "MONITORING", hasSuccessfulBid: true },
      { status: "BIDDING", hasSuccessfulBid: false },
      { status: "WON", hasSuccessfulBid: false },
    ]) {
      const v = cancelVerdict(row);
      assert.equal(v.ok, false);
      assert.ok(v.message.length > 0, `${row.status} の message が空`);
    }
  });

  // 陽性対照: 判定を「常に断る」に変えたらこのテストが落ちる。
  it("通す組み合わせが1つ以上ある(常に断る実装では落ちる)", () => {
    const passes = [
      { status: "SCHEDULED", hasSuccessfulBid: false },
      { status: "MONITORING", hasSuccessfulBid: false },
    ].filter((r) => cancelVerdict(r).ok);
    assert.equal(passes.length, 2);
  });
});
