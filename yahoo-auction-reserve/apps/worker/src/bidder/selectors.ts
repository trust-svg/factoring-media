// =============================================================
// ヤフオク入札フローのセレクタ定義
//
// P0 検証 (設計 §13) の状況。**検証済みと未検証が混在している**ので、
// 触るときは必ずこの表を更新すること。
//
// | セレクタ | 状態 | 根拠 |
// |---|---|---|
// | loginLink              | ✅ 検証済 | 2026-08-24 v1241268301。ログイン中0件 / 未ログイン2件 |
// | loggedInIndicator      | 🟡 1回のみ | 同上。ログイン中に a.mhdPcUserName__link を確認 |
//
// ⚠️ loginLink は入札フローだけでなく **セッションの生存確認**
// (jobs/verifySession.ts)でも使う。ここが外れると、失効を検知できないまま
// 入札の瞬間まで気づけない。判定の非対称性は src/sessionVerdict.ts を読むこと。
//
// | bidButton              | ✅ 検証済 | 同上。<button> でテキストのみが手掛かり |
// | priceInput             | ❌ 未検証 | Stage 2 (--stage2) が必要 |
// | bidConfirmButton       | ❌ 未検証 | 同上 |
// | bidSubmitButton        | ❌ 未検証 | 同上 |
// | wonIndicator           | ❌ 未検証 | 自分が入札した終了済み商品でないと出ない |
// | highestBidderIndicator | ❌ 未検証 | 同上 |
// | outbidIndicator        | ❌ 未検証 | 同上 |
// | watchlistLoginWall     | ❌ 未検証 | `npm run p0:probe -- --watchlist --anonymous` で陽性対照を取る |
// | watchlistItemLink      | ❌ 未検証 | `npm run p0:probe -- --watchlist`(ログイン状態で) |
// | watchlistNextPage      | ❌ 未検証 | 同上。2ページ目がある状態で確認すること |
//
// UI変更時はこのファイルだけ直せば済むよう、Playwright操作側には
// セレクタを直書きしないこと。
//
// --- 実測で分かった地雷 (2026-08-24) ---
//
// 1. `gv-Button--yimO_UuGzSZbwqISHVu4` のような `gv-` 系クラスの末尾はビルドハッシュ。
//    Yahoo 側のデプロイで変わるので **クラス名に依存しない**。
// 2. `a[href*='/jp/show/bid']` は入札履歴リンク `/jp/show/bid_hist` に前方一致する。
//    入札ボタンだと思って使うと、入札の瞬間に履歴ページへ飛ぶ。
// 3. 入札ボタンは `<a>` ではなく `<button>`。id / name / href が無く、
//    掴めるのは**アクセシブルネーム(表示テキスト)だけ**。
// 4. 「入札する」ボタンの個数は実行によって変わる(ログイン中1件 / 未ログイン2件。
//    画面下の固定バー分と思われる)。件数を前提にした判定を書かない。
// =============================================================

export const selectors = {
  // --- ログイン状態の判定 ---
  //
  // 判定の主役は **loginLink の不在**。実測でログイン中0件 / 未ログイン2件と
  // きれいに分かれた唯一の指標で、陰性対照(--anonymous)まで取れている。
  // loggedInIndicator は補助。ログイン中の1回でしか確認できていないので、
  // 「これが無い = 未ログイン」という判定には使わないこと(誤検知で入札を捨てる)。
  loggedInIndicator: "a.mhdPcUserName__link",
  loginLink: 'a[href*="login.yahoo.co.jp"]',

  // --- 商品ページ → 入札フォーム ---
  //
  // role セレクタを使うのは、実体が <button> で id も name も無く、
  // クラスがビルドハッシュ付きだから。exact=true は「まとめて入札する」等の
  // 部分一致を拾わないため。
  bidButton: 'role=button[name="入札する"][exact=true]',

  // ❌ 以下3つは未検証のプレースホルダのまま。
  // ボタンが <button> でリンクでないため、クリック後に別ページへ遷移するのか
  // モーダルが開くのかも未確定。--stage2 の実測で確定させること。
  priceInput: 'input[name="Bid_price"], input[name="price"]',
  bidConfirmButton: '[data-testid="bid-confirm"]',
  // 確認画面 → 入札確定
  bidSubmitButton: '[data-testid="bid-submit"], input[type="submit"][value*="入札"]',

  // --- 結果判定(終了後の商品ページ) ❌ 未検証 ---
  wonIndicator: "text=あなたが落札しました",
  highestBidderIndicator: "text=あなたが現在の最高額入札者です",
  outbidIndicator: "text=高値更新",

  // --- ウォッチリスト(ログイン必須) ❌ 未検証 ---
  //
  // ウォッチリストは未ログインだと商品が1件も出ず、ログイン画面へ飛ばされる。
  // つまり「0件」と「ログインが切れている」が **同じ見た目**になる。
  // watchlistLoginWall を先に見て、空リストと取得失敗を必ず区別すること
  // (区別しないと、セッション切れが「ウォッチリストが空になった」に化ける)。
  watchlistLoginWall: 'form[action*="login.yahoo.co.jp"], input[name="login"]',
  // 1商品ぶんのリンク。オークションIDを含む href を手掛かりにする
  watchlistItemLink: 'a[href*="/jp/auction/"]',
  // ページャの「次へ」。無ければ1ページで打ち切る
  watchlistNextPage: 'role=link[name="次へ"][exact=true]',
} as const;
