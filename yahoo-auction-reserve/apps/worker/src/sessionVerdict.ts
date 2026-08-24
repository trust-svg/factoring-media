/**
 * ヤフオク連携セッションが生きているかの判定(設計 §8-3)。
 *
 * DOM に触る部分と切り離した純粋関数にしてある。ブラウザ操作の中に
 * if を埋めると、判定の分岐をテストで固定できない。
 *
 * --- 判定に使ってよい signal / いけない signal ---
 *
 * 使ってよい(P0 実測 2026-08-24 で陰性対照まで取れている):
 *   - ログイン画面へのリダイレクト(到達 URL が login.yahoo.co.jp)
 *   - `loginLink` の **存在**(ログイン中0件 / 未ログイン2件ときれいに分かれた)
 *
 * 使ってはいけない:
 *   - `loggedInIndicator` の **不在**。ログイン中の1回でしか確認できておらず、
 *     ヘッダの実装が変わっただけで「全セッションが失効」に化ける。
 *     不在は UNKNOWN(判定しない)に倒す。
 *
 * EXPIRED は再連携を促す不可逆寄りの操作(予約が全部止まる)なので、
 * **陽性の証拠があるときだけ** 出す。取得失敗・判断不能は必ず UNKNOWN。
 */
export type SessionVerdict = "ACTIVE" | "EXPIRED" | "UNKNOWN";

export interface SessionSignals {
  /** 実際に到達した URL(リダイレクト後) */
  finalUrl: string;
  /** selectors.loginLink のヒット件数 */
  loginLinkCount: number;
  /** selectors.loggedInIndicator のヒット件数(補助。単独では判定しない) */
  loggedInIndicatorCount: number;
}

export interface VerdictResult {
  verdict: SessionVerdict;
  /** 通知・ログにそのまま出す説明 */
  reason: string;
}

const LOGIN_HOST_PATTERN = /(^|\/\/|\.)login\.yahoo\.co\.jp/i;

export function judgeSession(signals: SessionSignals): VerdictResult {
  if (LOGIN_HOST_PATTERN.test(signals.finalUrl)) {
    return { verdict: "EXPIRED", reason: "ログイン画面へリダイレクトされました" };
  }
  if (signals.loginLinkCount > 0) {
    return { verdict: "EXPIRED", reason: "ページにログインリンクが出ています(未ログイン状態)" };
  }
  if (signals.loggedInIndicatorCount > 0) {
    return { verdict: "ACTIVE", reason: "ログイン済みの表示を確認しました" };
  }
  // ログインリンクも無いがユーザー名も出ていない。ヘッダの実装変更・描画待ち・
  // 別レイアウトのいずれもありうるので、**ここでは失効にしない**。
  return {
    verdict: "UNKNOWN",
    reason: "ログイン状態を判断できませんでした(ログインリンクもユーザー名も検出できず)",
  };
}

export interface VerifyPlan {
  /** セッションを EXPIRED にして再連携を促すか */
  markExpired: boolean;
  /** lastVerifiedAt を進めるか(= 生きていると確認できた) */
  advanceVerifiedAt: boolean;
  /** true ならログを警告として出す(判定できていない状態が続くと危険) */
  warn: boolean;
}

/**
 * 判定結果を「DB に何をするか」へ変換する。
 *
 * ⚠️ `verdict !== "ACTIVE"` で失効にしない。UNKNOWN(判定不能)は
 * ページ構造が変わった日に全件で出る。そこで失効にすると、生きている
 * セッションが一斉に止まり、原因はログではなく「予約が動かない」という
 * 症状としてしか現れない。失効は EXPIRED の陽性判定だけに限る。
 */
export function planVerifyOutcome(result: VerdictResult): VerifyPlan {
  switch (result.verdict) {
    case "EXPIRED":
      return { markExpired: true, advanceVerifiedAt: false, warn: false };
    case "ACTIVE":
      return { markExpired: false, advanceVerifiedAt: true, warn: false };
    default:
      // 生存確認できていないので lastVerifiedAt も進めない。
      // 進めると「最終確認が古い」という唯一の異常サインが消える。
      return { markExpired: false, advanceVerifiedAt: false, warn: true };
  }
}
