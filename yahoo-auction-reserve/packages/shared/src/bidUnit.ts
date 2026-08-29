/**
 * ヤフオクの入札単位(現在価格帯ごとに決まる最小の上げ幅)。
 *
 * ✅ 出典: ヤフオク公式ヘルプ「入札単位について」(2026-08-29 確認)
 *   https://support.yahoo-net.jp/PccAuctions/s/article/H000008793
 *
 *   | 現在の価格        | 入札単位 |
 *   |-------------------|---------|
 *   | 1円～1,000円未満   | 10円    |
 *   | 1,000円～5,000円未満 | 100円  |
 *   | 5,000円～1万円未満  | 250円  |
 *   | 1万円～5万円未満    | 500円  |
 *   | 5万円～            | 1,000円 |
 *
 * 下の表はこの5行をそのまま写したもので、`under` は公式の「未満」に対応する
 * (1,000円ちょうどは 100円の段。境界の扱いは bidUnit.test.ts で固定してある)。
 *
 * ⚠️ ただし **実ページでの実測ではなく、提供元のドキュメントによる裏取り**である。
 * 公式ヘルプが古い可能性は残るので、入札フォームが出す「最低入札価格」と
 * 食い違ったらこの表ではなくフォーム側を正とすること
 * (`npm run p0:probe -- <URL> --stage2` で入札せずに確認画面手前まで行ける)。
 *
 * 誤っていた場合の壊れ方は方向で違う:
 * - 単位を **小さく** 見積もると、ヤフオク側に弾かれて入札が失敗する(気づける)
 * - 単位を **大きく** 見積もると、必要より高い額で入札してしまう(気づけない)
 * したがってこの表は「大きめに倒す」ことを避け、外れたら失敗する側に置く。
 */
const BID_UNIT_TABLE: Array<{ under: number; unit: number }> = [
  { under: 1_000, unit: 10 },
  { under: 5_000, unit: 100 },
  { under: 10_000, unit: 250 },
  { under: 50_000, unit: 500 },
  { under: Number.POSITIVE_INFINITY, unit: 1_000 },
];

export function yahooBidUnit(currentPrice: number): number {
  if (!Number.isFinite(currentPrice) || currentPrice < 0) return BID_UNIT_TABLE[0]!.unit;
  for (const row of BID_UNIT_TABLE) {
    if (currentPrice < row.under) return row.unit;
  }
  return BID_UNIT_TABLE[BID_UNIT_TABLE.length - 1]!.unit;
}

/**
 * 現在価格を上回るのに必要な最低額。
 *
 * ✅ 公式ヘルプ(上のURL)の記述がそのまま仕様:
 *   「最高入札額は、『現在の価格』(入札者がいない場合)または
 *     『現在の価格＋入札単位』(入札者がいる場合)以上なら、1円単位で決められます。」
 *
 * ここから2つが確定する:
 * - `bidCount === 0` のとき現在価格ちょうどで出せる(2026-08-29 に実装した分岐の裏取り)。
 *   開始価格1円・入札0件の商品で 11 円と算出していたのはこの分岐が無かったため。
 * - 「1円単位で決められます」= **単位の倍数へは切り上げない**。
 *   ヤフオクは上限額方式なので、端数のある額をそのまま出せる。
 *
 * ⚠️ 公式の条件は「入札**者**がいない場合」で、こちらが見ているのは
 * 埋め込みJSONの `bids`(入札**件数**)。件数0と入札者0は同値なので
 * 0 の判定としては一致する(件数>0 なら入札者も必ずいる)。
 * `biddersNum` と混ぜないこと(同じ商品で bids 10 / biddersNum 8 だった)。
 *
 * ⚠️ 件数が分からないとき(undefined)は **単位を足す側**に倒す。
 * 足りない額で出すと弾かれて入札が成立しないが、多い額は自動入札の上限が
 * 上がるだけで実害が小さいため。誤りのコストが方向で非対称なので、
 * 「分からない = 安全側」を既定にしておく。
 *
 * 入札件数は埋め込みJSONの `bids` から取れる(scraper.ts)。セレクタが
 * 要らないので、2026-08-29 に保留を解除した。
 */
export function minimumBidToBeat(currentPrice: number, bidCount?: number): number {
  if (bidCount === 0) return currentPrice;
  return currentPrice + yahooBidUnit(currentPrice);
}
