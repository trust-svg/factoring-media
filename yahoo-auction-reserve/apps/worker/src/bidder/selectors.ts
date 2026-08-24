// =============================================================
// ヤフオク入札フローのセレクタ定義
//
// !!! P0 検証対象 (設計 §13) !!!
// ここのセレクタはすべて実ページで未検証のプレースホルダ。
// UI変更時はこのファイルだけ直せば済むよう、Playwright操作側には
// セレクタを直書きしないこと。
// =============================================================

export const selectors = {
  // ログイン状態の判定(商品ページ上)
  loggedInIndicator: '[data-testid="user-menu"], .UserInfo',
  loginLink: 'a[href*="login.yahoo.co.jp"]',

  // 商品ページ → 入札フォーム
  bidButton: '[data-testid="bid-button"]',
  priceInput: 'input[name="Bid_price"], input[name="price"]',
  bidConfirmButton: '[data-testid="bid-confirm"]',
  // 確認画面 → 入札確定
  bidSubmitButton: '[data-testid="bid-submit"], input[type="submit"][value*="入札"]',

  // 結果判定(終了後の商品ページ)
  wonIndicator: "text=あなたが落札しました",
  highestBidderIndicator: "text=あなたが現在の最高額入札者です",
  outbidIndicator: "text=高値更新",
} as const;
