// =============================================================
// 入札の手前で、その予約が使う連携が生きているかを先に確かめる(案 C)
//
// なぜ要るか:
//   連携が切れていることに気づく機会は、これまで実質2つしか無かった。
//   (1) 6時間ごとの定期確認  (2) 入札の瞬間
//   (2) で分かっても手遅れで、(1) は **ACTIVE な連携しか走査しない**。
//
//   ⚠️ 後者が効かない穴が2つある。
//   - 直前に切れた場合: 最後の確認から6時間のあいだに切れると、次の確認は
//     入札より後になりうる
//   - **死んだ連携を指したまま残っている予約**: BidReservation.yahooSessionId は
//     予約を作った時点で固定される。再連携しても新しい連携は別レコードなので、
//     古い予約は失効した連携を指し続ける。定期確認は ACTIVE だけを見るので、
//     この予約は **永久に検査対象から外れる**(2026-09-22 実測。このときは
//     実行前の予約が0件だったので実害は出なかった)
//
// だから基準は「有効な連携」ではなく「**その予約が指している連携**」。
// =============================================================

import { monitorLeadSeconds } from "./constants";
import type { SessionStatusKey } from "./labels";

/**
 * monitor の起動の何ミリ秒前から事前確認を始めるか。
 *
 * 締切を endAt でなく **monitor の起動時刻** に取るのが要点。
 * snipeSecondsBefore は最大600秒まで伸ばせるので、endAt 基準にすると
 * 実行秒数の長い予約では監視が始まってから慌てることになる。
 */
export const PREFLIGHT_LEAD_MS = 60 * 60 * 1000;

/**
 * monitor の起動のこの時間前を切ったら、もうブラウザを開かない。
 *
 * ⚠️ 監視ジョブもヘッドレスブラウザを起動する。入札の直前に別のブラウザを
 * 立ち上げると Mac の資源を取り合う(Playwright が遅いときは資源枯渇を疑え、
 * という既知の落とし穴がある)。どのみち再連携する時間も無い。
 */
export const PREFLIGHT_BROWSER_CUTOFF_MS = 5 * 60 * 1000;

/** この時間内に生存確認が取れていれば、開き直さずそのまま信じる */
export const PREFLIGHT_TRUST_MS = 15 * 60 * 1000;

export type PreflightPlan =
  /** まだ窓に入っていない。何もしない(印も付けない) */
  | { kind: "wait" }
  /** 連携が有効でない。ブラウザは要らないので即通知する */
  | { kind: "notify-dead" }
  /** monitor の起動が近い。ブラウザは開かない */
  | { kind: "too-late" }
  /** 直近に確認が取れている。開かずに済ませる */
  | { kind: "trust" }
  /** 開いて確かめる */
  | { kind: "verify" };

export interface PreflightInput {
  now: Date;
  /** 予約の終了予定時刻 */
  endAt: Date;
  /** 終了の何秒前に入札するか */
  snipeSecondsBefore: number;
  /** **その予約が指している** 連携のいまの状態 */
  sessionStatus: SessionStatusKey;
  /** その連携の、最後に生存を確認できた時刻 */
  sessionLastVerifiedAt: Date | null;
}

export function planPreflight(input: PreflightInput): PreflightPlan {
  const { now, endAt, snipeSecondsBefore, sessionStatus, sessionLastVerifiedAt } = input;

  const monitorStartMs = endAt.getTime() - monitorLeadSeconds(snipeSecondsBefore) * 1000;
  const nowMs = now.getTime();

  // 窓の外では何もしない。終了の何日も前から「切れています」と鳴らさない
  // (通知が日常になると、本当に対応が要る日に読み飛ばされる)。
  if (nowMs < monitorStartMs - PREFLIGHT_LEAD_MS) return { kind: "wait" };

  // ⚠️ 死んでいる判定は打ち切りより **先**。通知にブラウザは要らないので、
  //    間に合わない時刻でも「この予約は失敗する」と伝えられる。
  if (sessionStatus !== "ACTIVE") return { kind: "notify-dead" };

  if (nowMs >= monitorStartMs - PREFLIGHT_BROWSER_CUTOFF_MS) return { kind: "too-late" };

  if (
    sessionLastVerifiedAt !== null &&
    nowMs - sessionLastVerifiedAt.getTime() < PREFLIGHT_TRUST_MS
  ) {
    return { kind: "trust" };
  }

  return { kind: "verify" };
}

/**
 * 事前確認の候補を DB から引くときの、終了時刻の上限(いまから何ミリ秒先までを見るか)。
 *
 * snipeSecondsBefore は予約ごとに違うので、SQL では monitor の起動時刻を
 * 計算できない。**いちばん早く窓が開く予約**(実行秒数が最大)に合わせて広めに
 * 引いておき、正確な判定は planPreflight() に任せる。
 *
 * ⚠️ 上限を狭く取ると、実行秒数の長い予約だけが一度も走査に載らないまま
 *    入札時刻を迎える。しかも「載らなかった」ことは何の記録にも残らない。
 */
export function preflightScanHorizonMs(maxSnipeSecondsBefore: number): number {
  return PREFLIGHT_LEAD_MS + monitorLeadSeconds(maxSnipeSecondsBefore) * 1000;
}
