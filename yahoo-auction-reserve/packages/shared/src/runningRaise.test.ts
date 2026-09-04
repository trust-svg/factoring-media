import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { validateRunningRaise, type RunningRaiseTarget } from "./runningRaise";
import { minimumBidToBeat } from "./bidUnit";

const NOW = new Date("2026-09-04T04:54:00+09:00").getTime();
const base: RunningRaiseTarget = {
  maxBidAmount: 34_500,
  currentPrice: 35_500,
  endAt: new Date("2026-09-04T04:59:03+09:00"),
};

describe("走行中の上限額引き上げ", () => {
  it("現在価格を上回れる額なら通す", () => {
    const required = minimumBidToBeat(35_500);
    const res = validateRunningRaise({ maxBidAmount: required }, base, NOW);
    assert.deepEqual(res, { ok: true, maxBidAmount: required });
  });

  it("上限額以外のキーが混ざっていたら断る(黙って無視しない)", () => {
    const res = validateRunningRaise(
      { maxBidAmount: 40_000, snipeSecondsBefore: 5 },
      base,
      NOW,
    );
    assert.equal(res.ok, false);
    assert.equal(res.ok === false && res.status, 409);
  });

  it("undefined のキーは混入とみなさない", () => {
    const res = validateRunningRaise(
      { maxBidAmount: 40_000, snipeSecondsBefore: undefined },
      base,
      NOW,
    );
    assert.equal(res.ok, true);
  });

  it("引き下げは断る(送信済みの入札は取り消せない)", () => {
    const res = validateRunningRaise({ maxBidAmount: 30_000 }, base, NOW);
    assert.equal(res.ok === false && res.status, 400);
  });

  it("同額は断る", () => {
    // ⚠️ 現在価格を null にして試すこと。現在価格が入ったままだと、
    // 同額は「入札単位に届かない」側の判定にも引っかかるので、
    // 引き上げ判定を <= から < に緩めても落ちない(実際に生き残った変異)。
    const res = validateRunningRaise(
      { maxBidAmount: base.maxBidAmount },
      { ...base, currentPrice: null },
      NOW,
    );
    assert.equal(res.ok === false && res.status, 400);
  });

  it("整数でなければ断る", () => {
    const res = validateRunningRaise({ maxBidAmount: 40_000.5 }, base, NOW);
    assert.equal(res.ok === false && res.status, 400);
  });

  it("現在価格は上回っていても入札単位に届かない額は断る", () => {
    // ⚠️ 現在価格 +1 円は「現在価格より高い」を満たすが入札できない。
    // 通してしまうと、増額したのに次のスナイプで見送られて負ける。
    const required = minimumBidToBeat(35_500);
    assert.ok(required > 35_501, "この価格帯の入札単位が1円になっている(前提が崩れた)");
    const res = validateRunningRaise({ maxBidAmount: 35_501 }, base, NOW);
    assert.equal(res.ok === false && res.status, 400);
  });

  it("現在価格が不明なら価格側の判定はしない", () => {
    // 現在価格 ¥35,500 を上回れない額。価格が分かっていれば断る額が、
    // 分かっていないときは通る = 価格側の判定を飛ばしていることの対照。
    const low = base.maxBidAmount + 1;
    assert.equal(
      validateRunningRaise({ maxBidAmount: low }, { ...base, currentPrice: null }, NOW).ok,
      true,
    );
    assert.equal(validateRunningRaise({ maxBidAmount: low }, base, NOW).ok, false);
  });

  it("終了済みなら断る", () => {
    const res = validateRunningRaise(
      { maxBidAmount: 40_000 },
      base,
      base.endAt.getTime(),
    );
    assert.equal(res.ok === false && res.status, 409);
  });

  it("終了1ミリ秒前なら通す(締切で塞がない)", () => {
    // ⚠️ 予約編集の締切(editDeadlineSeconds)をここに持ち込まないこと。
    // あの締切は「monitor が起動時の内容のまま走る」前提のもので、
    // 読み直すようになった今これを適用すると、高値更新に対応する手段が
    // 丸ごと無くなる。
    const res = validateRunningRaise(
      { maxBidAmount: 40_000 },
      base,
      base.endAt.getTime() - 1,
    );
    assert.equal(res.ok, true);
  });
});
