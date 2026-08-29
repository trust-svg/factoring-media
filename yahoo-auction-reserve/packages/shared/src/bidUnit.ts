/**
 * ヤフオクの入札単位(現在価格帯ごとに決まる最小の上げ幅)。
 *
 * ⚠️ **この表は P0 未検証**。公開情報から起こした値であり、実ページでの確認が
 * 済んでいない(設計 §13)。`npm run p0:probe -- <URL> --stage2` で入札フォームが
 * 出す「最低入札価格」と突き合わせて確定させること。
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
 * 現在価格を上回るために最低限必要な入札額。
 * 「現在価格 + 入札単位」が原則で、単位の倍数へは切り上げない
 * (ヤフオクは上限額方式なので、端数のある額をそのまま出せる)。
 */
/**
 * 現在価格を上回るのに必要な最低額。
 *
 * `bidCount` を渡すと入札0件の商品を正しく扱う。ヤフオクは入札が1件も
 * 無いとき現在価格(=開始価格)ちょうどで入札できるので、単位を足すと過大になる
 * (2026-08-29 に開始価格1円・入札0件の商品で 11 円と算出していた)。
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
