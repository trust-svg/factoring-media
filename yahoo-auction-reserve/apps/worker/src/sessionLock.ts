// 同一ヤフオクセッションからの入札を直列化する(設計 §7.4「1アカウント1並列」)。
//
// monitor ジョブ全体を直列化してはいけない。ウォームアップ〜自動延長ループは
// 最大30分続くので、同じアカウントで終了時刻が近い2件を予約した瞬間、
// 片方が **一度も入札されないまま終わる**。直列化するのは入札そのものだけ。
//
// ⚠️ ロックはこのプロセス内のメモリにしかない。worker を複数立てると直列化は
// 効かない(Telegram の getUpdates も 1 プロセス排他なので、そもそも worker は
// 1つで運用する前提。index.ts の注記を参照)。

/** 直列化のために待つ上限。これを超えたら諦めて並行実行する */
export const SESSION_LOCK_MAX_WAIT_MS = 20_000;

/**
 * 入札の実行そのものに使う時間として必ず残す余白。
 * ロック待ちでここまで食い潰すと、順番が回ってきた時には終了している。
 */
export const SESSION_LOCK_RESERVE_MS = 8_000;

/**
 * ロック待ちに使ってよい時間を、終了時刻から逆算する。
 *
 * ⚠️ **待ちきれないなら待たない。** 直列化はブロック回避のための予防で、
 * 入札を落とすことの代償の方がはるかに大きい。「安全のために待った結果
 * オークションが終わっていた」が起きない上限をここで決める。
 */
export function sessionLockWaitMs(nowMs: number, endAtMs: number): number {
  const budget = endAtMs - nowMs - SESSION_LOCK_RESERVE_MS;
  if (budget <= 0) return 0;
  return Math.min(budget, SESSION_LOCK_MAX_WAIT_MS);
}

export interface SessionLease {
  /** 直列化できたか。false = 待ちきれず並行実行している */
  serialized: boolean;
  waitedMs: number;
  release: () => void;
}

const holders = new Map<string, Promise<void>>();

/**
 * セッション単位のロックを取る。取れなくても **必ず返る**(その場合
 * `serialized: false`)。呼び出し側は結果に関わらず処理を続けてよい。
 */
export async function acquireSessionLock(
  key: string,
  maxWaitMs: number,
): Promise<SessionLease> {
  const startedAt = Date.now();

  for (;;) {
    const current = holders.get(key);
    if (!current) break;

    const remaining = maxWaitMs - (Date.now() - startedAt);
    if (remaining <= 0) {
      // 諦めるときは holders を触らない。ここで自分を登録すると、実際に
      // 動いている側のロックを追い出して以後の直列化が全部壊れる。
      return { serialized: false, waitedMs: Date.now() - startedAt, release: () => {} };
    }
    await raceTimeout(current, remaining);
    // ループで holders を取り直す。同じ待ち行列に2人いた場合、
    // 先に取った方が登録済みなので、ここで抜けると二重実行になる。
  }

  let finish!: () => void;
  const mine = new Promise<void>((resolve) => {
    finish = resolve;
  });
  holders.set(key, mine);

  let released = false;
  return {
    serialized: true,
    waitedMs: Date.now() - startedAt,
    release: () => {
      if (released) return; // 二重 release で他人のロックを消さない
      released = true;
      if (holders.get(key) === mine) holders.delete(key);
      finish();
    },
  };
}

function raceTimeout(p: Promise<void>, ms: number): Promise<void> {
  return new Promise((resolve) => {
    // ⚠️ unref() してはいけない。これが唯一の保留中タイマーになると
    // イベントループが先に空になり、**待ちが永久に解決しない**
    // (テストでは "Promise resolution is still pending" として現れた)。
    // 待ち時間は最長でも SESSION_LOCK_MAX_WAIT_MS なので放置してよい。
    const timer = setTimeout(resolve, ms);
    void p.then(() => {
      clearTimeout(timer);
      resolve();
    });
  });
}
