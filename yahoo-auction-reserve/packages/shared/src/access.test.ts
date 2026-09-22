import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import {
  LOGIN_BLOCK_MS,
  LOGIN_MAX_FAILURES,
  LOGIN_WINDOW_MS,
  canRegister,
  checkLoginThrottle,
  recordLoginFailure,
} from "./access";

describe("canRegister", () => {
  it("ユーザーが1人も居なければ許可(初回セットアップ)", () => {
    assert.equal(canRegister({ allowFlag: undefined, existingUserCount: 0 }).allowed, true);
  });

  it("既に利用者が居れば、環境変数なしでは断る", () => {
    // ここが true になると、外に出した瞬間に誰でも登録できる
    const v = canRegister({ allowFlag: undefined, existingUserCount: 1 });
    assert.equal(v.allowed, false);
    assert.ok(v.reason);
  });

  it("ALLOW_REGISTRATION=true のときだけ明示的に開く", () => {
    assert.equal(canRegister({ allowFlag: "true", existingUserCount: 3 }).allowed, true);
    // "1" や "yes" は開けない(意図しない文字列で開くと気づけない)
    assert.equal(canRegister({ allowFlag: "1", existingUserCount: 3 }).allowed, false);
    assert.equal(canRegister({ allowFlag: "false", existingUserCount: 3 }).allowed, false);
  });
});

describe("checkLoginThrottle", () => {
  const t0 = 1_700_000_000_000;

  it("記録が無ければ通す", () => {
    assert.equal(checkLoginThrottle(undefined, t0).allowed, true);
  });

  it("上限未満なら通す", () => {
    const r = { failures: LOGIN_MAX_FAILURES - 1, windowStartedAt: t0 };
    assert.equal(checkLoginThrottle(r, t0 + 1000).allowed, true);
  });

  it("上限に達したらブロックし、待ち時間を返す", () => {
    const r = { failures: LOGIN_MAX_FAILURES, windowStartedAt: t0 };
    const v = checkLoginThrottle(r, t0 + 60_000);
    assert.equal(v.allowed, false);
    assert.ok(v.retryAfterSec > 0);
    assert.ok(v.retryAfterSec <= LOGIN_BLOCK_MS / 1000);
  });

  it("窓を過ぎれば自動で解除される(手動解除を要求しない)", () => {
    const r = { failures: LOGIN_MAX_FAILURES + 10, windowStartedAt: t0 };
    assert.equal(checkLoginThrottle(r, t0 + LOGIN_WINDOW_MS).allowed, true);
  });
});

describe("recordLoginFailure", () => {
  const t0 = 1_700_000_000_000;

  it("最初の失敗で窓が始まる", () => {
    const r = recordLoginFailure(undefined, t0);
    assert.deepEqual(r, { failures: 1, windowStartedAt: t0 });
  });

  it("窓の中では回数だけ増え、起点は動かない", () => {
    const r = recordLoginFailure({ failures: 2, windowStartedAt: t0 }, t0 + 1000);
    assert.equal(r.failures, 3);
    // 起点が動くと、叩き続ける相手に対して永久ロックアウトになる
    assert.equal(r.windowStartedAt, t0);
  });

  it("ブロック中に叩かれても解除時刻は延びない", () => {
    let rec = { failures: LOGIN_MAX_FAILURES, windowStartedAt: t0 };
    for (let i = 0; i < 20; i++) rec = recordLoginFailure(rec, t0 + 1000 * i);
    // 窓の終わりには必ず解除される(攻撃者が他人を締め出せない)
    assert.equal(checkLoginThrottle(rec, t0 + LOGIN_WINDOW_MS).allowed, true);
  });

  it("窓を過ぎた後の失敗は新しい窓として数え直す", () => {
    const r = recordLoginFailure(
      { failures: LOGIN_MAX_FAILURES, windowStartedAt: t0 },
      t0 + LOGIN_WINDOW_MS + 1,
    );
    assert.equal(r.failures, 1);
  });
});
