import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { BID_STEPS_RESERVE_MS, SETTLE_MAX_MS, settleBudgetMs } from "./settle";

// 描画待ちに使ってよい時間の計算。
//
// ここが守っているのは「入札に間に合わなくなるまで待たない」こと。
// snipeSecondsBefore は 5〜600秒(既定30)なので、固定で15秒待つ実装は
// 短い予約だけを黙って落とす。落ちるのは入札の瞬間の1回きりで、
// 「TIMEOUT」としか残らないので事後に理由が分からない。

describe("settleBudgetMs", () => {
  it("終了時刻が分からないときは上限をそのまま使う", () => {
    assert.equal(settleBudgetMs({}), SETTLE_MAX_MS);
  });

  it("残り時間が十分あれば上限まで待つ", () => {
    assert.equal(settleBudgetMs({ remainingMs: 60_000 }), SETTLE_MAX_MS);
  });

  it("残り時間が上限より短ければ、入札の手順ぶんを残して切り詰める", () => {
    // 5秒前入札(最短)。ここが 15_000 のままだと入札が実行されない。
    assert.equal(settleBudgetMs({ remainingMs: 5_000 }), 5_000 - BID_STEPS_RESERVE_MS);
  });

  it("入札の手順ぶんも残っていなければ 0(=待たない)", () => {
    assert.equal(settleBudgetMs({ remainingMs: BID_STEPS_RESERVE_MS }), 0);
  });

  it("終了時刻を過ぎていても負の値は返さない", () => {
    // 負の値をそのまま Playwright の timeout に渡すと例外になる。
    // 0 も `timeout: 0` は **無制限** の意味なので、呼び出し側は
    // 0 のときに待つ処理そのものを飛ばす必要がある。
    assert.equal(settleBudgetMs({ remainingMs: -10_000 }), 0);
  });
});
