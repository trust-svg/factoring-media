import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import {
  SESSION_LOCK_MAX_WAIT_MS,
  acquireSessionLock,
  sessionLockWaitMs,
} from "./sessionLock";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

describe("sessionLockWaitMs", () => {
  const now = 1_000_000;

  it("終了まで十分あれば上限まで待てる", () => {
    assert.equal(sessionLockWaitMs(now, now + 10 * 60_000), SESSION_LOCK_MAX_WAIT_MS);
  });

  it("終了が近ければ、入札に使う余白を残した分しか待たない", () => {
    const ms = sessionLockWaitMs(now, now + 10_000);
    assert.ok(ms > 0);
    assert.ok(ms < 10_000, "残り時間より短いこと");
  });

  it("余白すら無ければ待たない(待つと入札を落とす)", () => {
    assert.equal(sessionLockWaitMs(now, now + 3_000), 0);
  });

  it("すでに終了時刻を過ぎていても負の値を返さない", () => {
    assert.equal(sessionLockWaitMs(now, now - 60_000), 0);
  });
});

describe("acquireSessionLock", () => {
  it("同じセッションの入札は重ならない", async () => {
    const key = "s-serial";
    const order: string[] = [];

    const first = (async () => {
      const lease = await acquireSessionLock(key, 5_000);
      order.push("A:in");
      await sleep(30);
      order.push("A:out");
      lease.release();
    })();
    // A がロックを取ってから B を始める
    await sleep(5);
    const second = (async () => {
      const lease = await acquireSessionLock(key, 5_000);
      assert.equal(lease.serialized, true);
      order.push("B:in");
      order.push("B:out");
      lease.release();
    })();

    await Promise.all([first, second]);
    assert.deepEqual(order, ["A:in", "A:out", "B:in", "B:out"]);
  });

  it("別セッションは待たされない", async () => {
    const held = await acquireSessionLock("s-other-1", 5_000);
    const t0 = Date.now();
    const lease = await acquireSessionLock("s-other-2", 5_000);
    assert.equal(lease.serialized, true);
    assert.ok(Date.now() - t0 < 50);
    lease.release();
    held.release();
  });

  it("待ちきれなければ諦めて実行する(入札を落とさない)", async () => {
    const key = "s-timeout";
    const held = await acquireSessionLock(key, 5_000);

    const lease = await acquireSessionLock(key, 20);
    // ここが true になったら、待ちが無制限になっている
    assert.equal(lease.serialized, false);

    // 諦めた側は holders を書き換えないので、本来の保持者が生きている
    lease.release();
    const third = acquireSessionLock(key, 500);
    let resolvedEarly = false;
    void third.then(() => {
      resolvedEarly = true;
    });
    await sleep(30);
    assert.equal(resolvedEarly, false, "諦めた側の release で解放されてはいけない");

    held.release();
    assert.equal((await third).serialized, true);
    (await third).release();
  });

  it("release を二度呼んでも次の保持者を壊さない", async () => {
    const key = "s-double-release";
    const first = await acquireSessionLock(key, 1_000);
    first.release();
    first.release();

    const second = await acquireSessionLock(key, 1_000);
    assert.equal(second.serialized, true);
    first.release(); // 遅れて届いた二重 release
    const t0 = Date.now();
    const third = acquireSessionLock(key, 40);
    assert.equal((await third).serialized, false, "second のロックは生きているはず");
    assert.ok(Date.now() - t0 >= 20);
    second.release();
  });
});
