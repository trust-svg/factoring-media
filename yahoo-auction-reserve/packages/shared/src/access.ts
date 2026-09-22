// =============================================================
// 公開時のアクセス制御(外出先から使うために必要な最低限)
//
// このアプリはヤフオクのログイン Cookie を預かる。外から到達できる場所に
// 置くなら、①誰でも新規登録できる状態を閉じる ②ログインの総当りを止める
// の2つが前提になる。どちらも「設定し忘れると開いたまま」にならないよう、
// 既定値を安全側にしてある。
// =============================================================

export interface RegistrationContext {
  /** 環境変数 ALLOW_REGISTRATION の生値 */
  allowFlag: string | undefined;
  /** 既に登録済みのユーザー数 */
  existingUserCount: number;
}

export interface RegistrationVerdict {
  allowed: boolean;
  /** 断るときの理由(そのまま画面に出す) */
  reason?: string;
}

/**
 * 新規登録を受け付けてよいか。
 *
 * ⚠️ 既定は「ユーザーが0人のときだけ許可」。環境変数の設定を前提にすると、
 * 設定し忘れた日に登録が開いたままになる。初回セットアップが済んだ時点で
 * 自動的に閉じる形にして、開けたいときだけ ALLOW_REGISTRATION=true を立てる。
 */
export function canRegister(ctx: RegistrationContext): RegistrationVerdict {
  if (ctx.allowFlag === "true") return { allowed: true };
  if (ctx.existingUserCount === 0) return { allowed: true };
  return {
    allowed: false,
    reason:
      "新規登録は受け付けていません(既に利用者が登録済みです)。追加したい場合は ALLOW_REGISTRATION=true を設定してください",
  };
}

/** 何回失敗したらブロックするか */
export const LOGIN_MAX_FAILURES = 5;
/** 失敗回数を数える窓 */
export const LOGIN_WINDOW_MS = 15 * 60 * 1000;
/** ブロックする長さ */
export const LOGIN_BLOCK_MS = 15 * 60 * 1000;

export interface LoginAttemptRecord {
  failures: number;
  /** 窓の起点(最初の失敗時刻) */
  windowStartedAt: number;
}

export interface ThrottleVerdict {
  allowed: boolean;
  /** ブロック中に「あと何秒待てばよいか」。allowed=true のときは 0 */
  retryAfterSec: number;
}

/**
 * ログインを試してよいか。
 *
 * ⚠️ 呼ぶのは **パスワード照合より前**。「ユーザーが見つからない」等の
 * 早期 return の後ろに置くと、存在しないメールアドレスへの総当りだけ
 * 無制限に通る(しかも画面上は正常に見える)。
 */
export function checkLoginThrottle(
  record: LoginAttemptRecord | undefined,
  now: number,
): ThrottleVerdict {
  if (!record) return { allowed: true, retryAfterSec: 0 };
  const elapsed = now - record.windowStartedAt;
  // 窓を過ぎていれば失敗回数は無かったことにする
  if (elapsed >= LOGIN_WINDOW_MS) return { allowed: true, retryAfterSec: 0 };
  if (record.failures < LOGIN_MAX_FAILURES) return { allowed: true, retryAfterSec: 0 };
  const remainMs = record.windowStartedAt + LOGIN_BLOCK_MS - now;
  return { allowed: false, retryAfterSec: Math.max(1, Math.ceil(remainMs / 1000)) };
}

/**
 * 失敗を1回記録する。
 *
 * ⚠️ ブロック中の試行も **数え直さない**。ブロック中の失敗で窓の起点を
 * 進めると、叩き続ける相手には永久ブロック、正規の利用者には解除されない
 * ロックアウトになる(攻撃者が他人を締め出す道具になる)。
 */
export function recordLoginFailure(
  record: LoginAttemptRecord | undefined,
  now: number,
): LoginAttemptRecord {
  if (!record || now - record.windowStartedAt >= LOGIN_WINDOW_MS) {
    return { failures: 1, windowStartedAt: now };
  }
  return { failures: record.failures + 1, windowStartedAt: record.windowStartedAt };
}
