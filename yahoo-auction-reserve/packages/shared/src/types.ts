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
  | "WON"
  | "LOST"
  | "FAILED"
  | "EXPIRED"
  | "SESSION_EXPIRED";
