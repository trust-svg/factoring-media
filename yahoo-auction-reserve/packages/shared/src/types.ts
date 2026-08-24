// ブラウザから持ち込むCookie 1件分(Playwright の Cookie 形式のサブセット)
export interface YahooCookie {
  name: string;
  value: string;
  domain: string;
  path?: string;
  expires?: number;
  httpOnly?: boolean;
  secure?: boolean;
  sameSite?: "Strict" | "Lax" | "None";
}

// 商品ページから取得できた情報(取れない項目は undefined のまま返す)
export interface AuctionInfo {
  auctionId: string;
  url: string;
  title?: string;
  imageUrl?: string;
  sellerName?: string;
  currentPrice?: number;
  endAt?: Date;
  hasAutoExtension?: boolean;
  isClosed?: boolean;
}

export type NotificationType =
  | "WON" // 落札した
  | "LOST" // 高値更新されて落札できなかった
  | "FAILED" // 入札の実行自体に失敗した
  | "EXPIRED" // 現在価格が上限額を超えたので入札しなかった
  | "SESSION_EXPIRED" // ヤフオク連携が切れている
  | "REMINDER" // 終了N分前のリマインド
  | "AUTO_RAISED" // 自動増額して入札しなおした
  | "RAISE_DECLINED" // 増額できる状態ではなかった(天井到達・回数切れ・承認なし)
  | "APPROVAL_REQUEST" // 増額してよいか Telegram で聞いている
  | "GROUP_CANCELLED" // 同じグループの他を落札したので取りやめた
  | "DAILY_SUMMARY"; // 毎日の稼働サマリ(届かないこと自体が異常の合図)

// 通知の系統。ユーザー設定(NotificationSetting)で切れるのは RESULT と ERROR だけで、
// ACTION(承認依頼)は切れない。入札の可否を決める問い合わせなので、
// 届かない = 増額しないという実害に直結する。
export type NotificationCategory = "RESULT" | "ERROR" | "REMINDER" | "ACTION" | "SUMMARY";

export const NOTIFICATION_CATEGORY: Record<NotificationType, NotificationCategory> = {
  WON: "RESULT",
  LOST: "RESULT",
  AUTO_RAISED: "RESULT",
  GROUP_CANCELLED: "RESULT",
  FAILED: "ERROR",
  EXPIRED: "ERROR",
  SESSION_EXPIRED: "ERROR",
  RAISE_DECLINED: "ERROR",
  REMINDER: "REMINDER",
  APPROVAL_REQUEST: "ACTION",
  DAILY_SUMMARY: "SUMMARY",
};
