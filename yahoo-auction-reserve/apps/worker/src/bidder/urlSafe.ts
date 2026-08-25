// URL をログ・レポートに出すときの伏せ字。
//
// なぜ要るか: ヤフオクの導線 URL には `.done=`(戻り先)のほか、
// `crumb` / `.crumb` のような **使い回せる値** が乗る。ウォッチリストの URL を
// 探すためにリンクを片端からレポートへ書き出すので、そのまま出すと
// 秘匿情報がレポートファイルに残る(設計 §8: Cookie 等をログに出さない)。
//
// ⚠️ 方針は「既定で伏せる」。危険なパラメータ名を列挙して伏せる方式だと、
//    知らない名前が増えた日に黙って漏れる。**通してよい名前だけ** を並べ、
//    それ以外は値を伏せる。伏せすぎの代償はレポートが少し読みにくいだけ。

/**
 * 値をそのまま出してよいクエリパラメータ名。
 * 「どのページか」を特定するのに要るナビゲーション用のものだけ。
 */
export const SAFE_QUERY_KEYS = new Set([
  "select",
  "tab",
  "page",
  "b",
  "n",
  "sort",
  "order",
]);

export const REDACTED = "***";

/**
 * ログに出せる形の URL を返す。
 * パースできない文字列はそのまま返さず、丸ごと伏せる(何が入っているか
 * 分からないものを出さない)。
 */
export function redactUrl(raw: string): string {
  let u: URL;
  try {
    u = new URL(raw);
  } catch {
    return REDACTED;
  }

  const params = [...u.searchParams.keys()];
  const query = params
    .map((k) => `${k}=${SAFE_QUERY_KEYS.has(k) ? u.searchParams.get(k) : REDACTED}`)
    .join("&");

  // フラグメントも値が乗りうるので落とす
  return `${u.origin}${u.pathname}${query ? `?${query}` : ""}`;
}
