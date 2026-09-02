// DB の enum 値 → 画面表示ラベル。
//
// 以前はダッシュボードと予約詳細に同じ表が2つあり、`Record<string, string>` +
// `?? status` のフォールバック付きだった。この形は enum が増えたときに
// **生の enum 名が画面に出るだけで型エラーにならない**(片方だけ直して気づかない)。
// ここに集約したうえで、キーをリテラル union にして網羅を型で強制する。
//
// この union は packages/db/prisma/schema.prisma の enum と一致させること。
// ズレは apps/web/lib/labels-check.ts の型アサーションで検出する
// (shared は @yar/db に依存しないので、突き合わせは web 側で行う)。

export type ReservationStatusKey =
  | "SCHEDULED"
  | "MONITORING"
  | "BIDDING"
  | "WON"
  | "LOST"
  | "FAILED"
  | "CANCELLED"
  | "EXPIRED"
  | "DRY_RUN";

export const RESERVATION_STATUS_LABEL: Record<ReservationStatusKey, string> = {
  SCHEDULED: "待機中",
  MONITORING: "実行準備中",
  BIDDING: "入札中",
  WON: "落札",
  LOST: "落札ならず",
  FAILED: "失敗",
  CANCELLED: "キャンセル",
  EXPIRED: "スキップ",
  DRY_RUN: "テスト実行(入札していません)",
};

/**
 * もう動いていないので、**同じ商品をもう一度予約してよい** 状態。
 *
 * ⚠️ 「終わった予約」(ダッシュボードの結果タブ)とは別物。WON はここに
 * 入れない — 落札済みの商品を予約し直すことはできない。
 *
 * ⚠️ この一覧はもともと予約APIの中にだけ書かれていて、ウォッチリスト画面は
 * 「予約が1件でもあれば予約済み」と見ていた。結果、キャンセルした商品の行から
 * 「予約する」も「一覧から消す」も消え、**ウォッチリストからは二度と予約
 * できなくなっていた**(2026-09-02 報告)。API 側は最初から再登録を許して
 * いたので、壊れていたのは画面だけ。同じ判断を2箇所で書かないためここに置く。
 */
export const RESERVATION_REBOOKABLE_STATUSES: ReservationStatusKey[] = [
  "CANCELLED",
  "FAILED",
  "LOST",
  "EXPIRED",
  // テスト実行は「本番の予約をまだしていない」状態。ここに入れ忘れると
  // テスト実行するほど本番の予約ができなくなる。
  "DRY_RUN",
];

/** 予約し直せる状態か(未知の値は「動いている」側に倒す) */
export function isRebookableReservation(status: string): boolean {
  return (RESERVATION_REBOOKABLE_STATUSES as string[]).includes(status);
}

export type AttemptOutcomeKey =
  | "SUCCESS"
  | "OUTBID"
  | "PRICE_OVER_LIMIT"
  | "SESSION_EXPIRED"
  | "PAGE_ERROR"
  | "TIMEOUT"
  | "AUTO_RAISED"
  | "RAISE_DECLINED"
  | "GROUP_CANCELLED"
  | "DRY_RUN";

export const ATTEMPT_OUTCOME_LABEL: Record<AttemptOutcomeKey, string> = {
  SUCCESS: "入札成功",
  OUTBID: "高値更新された",
  PRICE_OVER_LIMIT: "上限額オーバーのため見送り",
  SESSION_EXPIRED: "ヤフオクのログインが切れていた",
  PAGE_ERROR: "ページ操作に失敗",
  TIMEOUT: "時間内に完了しなかった",
  AUTO_RAISED: "増額して入札しなおした",
  RAISE_DECLINED: "増額しなかった",
  GROUP_CANCELLED: "同じグループの他の商品を落札したため取りやめ",
  DRY_RUN: "テスト実行(確認画面まで到達・確定は押していない)",
};

export type SessionStatusKey = "ACTIVE" | "EXPIRED" | "INVALID";

export const SESSION_STATUS_LABEL: Record<SessionStatusKey, string> = {
  ACTIVE: "有効",
  EXPIRED: "失効(要再連携)",
  INVALID: "不正",
};


export type AutoRaiseModeKey = "OFF" | "AUTO" | "APPROVAL";

export const AUTO_RAISE_MODE_LABEL: Record<AutoRaiseModeKey, string> = {
  OFF: "増額しない",
  AUTO: "自動で増額",
  APPROVAL: "Telegram で承認してから増額",
};

export type ApprovalStatusKey = "PENDING" | "APPROVED" | "REJECTED" | "TIMEOUT";

export const APPROVAL_STATUS_LABEL: Record<ApprovalStatusKey, string> = {
  PENDING: "承認待ち",
  APPROVED: "承認された",
  REJECTED: "見送りを選択",
  TIMEOUT: "期限までに応答なし(増額せず)",
};


export type SessionVerificationKind =
  | "VERIFIED" // 一度は生存を確認できている(時刻を出す)
  | "PENDING" // まだ一度も確認を試みていない(登録直後。待てば結果が出る)
  | "INCONCLUSIVE"; // 試したが判定できなかった(待っても出ない)

/**
 * 連携の「最終確認」欄に何を出すかを決める。
 *
 * ⚠️ PENDING と INCONCLUSIVE を混ぜない。どちらも lastVerifiedAt が null だが
 * 意味が正反対で、前者は待てば結果が出る・後者は待っても永久に出ない
 * (ページ構造が変わってセレクタが外れている)。両方を「未実施」と表示すると、
 * **判定機構が壊れている状態が「まだ順番が来ていないだけ」に見えて放置される**。
 */
export function sessionVerificationKind(
  lastVerifiedAt: Date | string | null | undefined,
  lastVerifyAttemptAt: Date | string | null | undefined,
): SessionVerificationKind {
  if (lastVerifiedAt) return "VERIFIED";
  if (lastVerifyAttemptAt) return "INCONCLUSIVE";
  return "PENDING";
}

export const SESSION_VERIFICATION_LABEL: Record<SessionVerificationKind, string> = {
  VERIFIED: "確認済み",
  PENDING: "確認中(まもなく判定します)",
  INCONCLUSIVE: "判定できませんでした(セレクタの確認が必要)",
};
