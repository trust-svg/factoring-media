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
  // 即決価格。設定されていない出品の方が多いので、無いことは undefined。
  // ⚠️ 0 を入れない。0 は「0円で即決できる」に読めてしまう。
  buyNowPrice?: number;
  endAt?: Date;
  hasAutoExtension?: boolean;
  isClosed?: boolean;
  // --- 判断材料。取れなかった項目は undefined のままにする ---
  // shippingFee は 0 が「送料無料」なので、undefined と 0 を混同しないこと。
  shippingFee?: number;
  shippingNote?: string; // 金額を確定できなかったときの原文(「落札者負担」など)
  sellerRating?: number; // 良い評価の割合(%)
  sellerRatingCount?: number; // 評価総数
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
  | "DAILY_SUMMARY" // 毎日の稼働サマリ(届かないこと自体が異常の合図)
  | "DRY_RUN"; // テスト実行が確認画面まで到達した(実際には入札していない)

// 通知の系統。ユーザー設定(NotificationSetting)で切れるのは RESULT と ERROR だけで、
// ACTION(承認依頼)は切れない。入札の可否を決める問い合わせなので、
// 届かない = 増額しないという実害に直結する。
// TEST(テスト実行の結果)を RESULT に入れないのは、結果通知を切っている
// ユーザーがテスト実行すると **何も届かないまま終わる** ため。
// テスト実行はユーザーが明示的に仕込んだ検証で、結果が届かないと
// 「予約したのに何も起きなかった」と区別が付かない。
export type NotificationCategory =
  | "RESULT"
  | "ERROR"
  | "REMINDER"
  | "ACTION"
  | "SUMMARY"
  | "TEST";

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
  DRY_RUN: "TEST",
};
