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
  | "EXPIRED";

export const RESERVATION_STATUS_LABEL: Record<ReservationStatusKey, string> = {
  SCHEDULED: "待機中",
  MONITORING: "実行準備中",
  BIDDING: "入札中",
  WON: "落札",
  LOST: "落札ならず",
  FAILED: "失敗",
  CANCELLED: "キャンセル",
  EXPIRED: "スキップ",
};

export type AttemptOutcomeKey =
  | "SUCCESS"
  | "OUTBID"
  | "PRICE_OVER_LIMIT"
  | "SESSION_EXPIRED"
  | "PAGE_ERROR"
  | "TIMEOUT"
  | "AUTO_RAISED"
  | "RAISE_DECLINED"
  | "GROUP_CANCELLED";

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
