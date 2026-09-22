import {
  checkLoginThrottle,
  recordLoginFailure,
  type LoginAttemptRecord,
  type ThrottleVerdict,
} from "@yar/shared";

// ログイン失敗の記録。**プロセス内メモリ**(単一インスタンス前提の MVP)。
// 再起動で消えるが、bcrypt cost 12 と併せれば総当りの速度は十分落ちる。
// 複数インスタンスで動かすようになったら Redis へ移すこと。
const store = new Map<string, LoginAttemptRecord>();
// 鍵の数に上限を置く。置かないと、適当なメールアドレスを送り続けるだけで
// メモリを食い潰せてしまう(ブロック機構そのものが攻撃面になる)。
const MAX_KEYS = 5_000;

/**
 * リクエスト元 IP。プロキシ(Tailscale Serve / Cloudflare)の後ろでは
 * ヘッダ経由になる。取れなければ IP 側の制限は諦める(メール側は効く)。
 *
 * ⚠️ 取れないときに固定文字列で1つの鍵に寄せない。全員が同じバケツに入り、
 * 誰かの失敗で正規の利用者がロックアウトされる。
 */
export function clientIp(headers: Headers): string | null {
  const xff = headers.get("x-forwarded-for");
  const first = xff?.split(",")[0]?.trim();
  return first || headers.get("cf-connecting-ip") || null;
}

export function throttleKeys(email: unknown, ip: string | null): string[] {
  const keys: string[] = [];
  if (typeof email === "string" && email) keys.push(`email:${email.toLowerCase()}`);
  if (ip) keys.push(`ip:${ip}`);
  return keys;
}

export function checkThrottle(keys: string[], now = Date.now()): ThrottleVerdict {
  let worst: ThrottleVerdict = { allowed: true, retryAfterSec: 0 };
  for (const k of keys) {
    const v = checkLoginThrottle(store.get(k), now);
    if (!v.allowed && v.retryAfterSec > worst.retryAfterSec) worst = v;
  }
  return worst;
}

export function markFailure(keys: string[], now = Date.now()): void {
  for (const k of keys) {
    if (!store.has(k) && store.size >= MAX_KEYS) continue;
    store.set(k, recordLoginFailure(store.get(k), now));
  }
}

export function clearFailures(keys: string[]): void {
  for (const k of keys) store.delete(k);
}
