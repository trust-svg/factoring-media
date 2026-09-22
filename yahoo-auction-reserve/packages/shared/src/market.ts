// =============================================================
// 落札相場(ヤフオクの「落札済み」検索)からの中央値算出
//
// ⚠️ セレクタ・正規表現・検索URLは未検証のプレースホルダ。
//   P0 検証(設計 §13)で実ページと突き合わせるまで「動く保証はない」前提。
//   ただし median / buildMarketQuery / parseClosedPrices は純粋関数なので、
//   HTML さえ差し替えれば判断ロジック自体はテストで守れる。
// =============================================================

/** ヤフオクの落札相場検索URL。検索語はタイトルから機械的に作る。 */
export function closedSearchUrl(query: string): string {
  const p = encodeURIComponent(query);
  return `https://auctions.yahoo.co.jp/closedsearch/closedsearch?p=${p}&va=${p}`;
}

const NOISE_PATTERN =
  /[【】\[\]（）()《》「」『』♪★☆※!！?？…、,，\/|｜~〜+＋]/g;
// 相場をぼかす語(状態・付随物)。残すと「ジャンク品」ばかりが当たる。
const STOPWORDS = [
  "新品",
  "中古",
  "未使用",
  "美品",
  "ジャンク",
  "訳あり",
  "送料無料",
  "送料込",
  "即決",
  "希少",
  "レア",
  "限定",
  "セット",
  "まとめ",
];

/**
 * 商品タイトルから検索語を作る。
 *
 * ⚠️ **語を削りすぎない**。ヤフオクの落札検索は AND なので、語を増やすほど
 * 件数が減って中央値の母数が消える。一方で状態語(美品/ジャンク)を残すと
 * 別の相場を見ることになる。ここでは記号とノイズ語だけ落として、
 * 先頭から数語に絞る。
 */
export function buildMarketQuery(title: string, maxWords = 6): string {
  const words = title
    .replace(NOISE_PATTERN, " ")
    .split(/\s+/)
    .map((w) => w.trim())
    .filter((w) => w.length > 0 && !STOPWORDS.includes(w));
  return words.slice(0, maxWords).join(" ");
}

/** 落札価格の一覧を HTML から拾う(取れた分だけ返す)。 */
export function parseClosedPrices(html: string): number[] {
  const prices: number[] = [];
  // 「落札価格 1,234円」「<span class="...price...">1,234円</span>」の両方に当てる。
  // class 名の大小はヤフオク側の都合で変わるので i を付ける(Price / priceValue)。
  const re = /(?:落札価格|price[^>]*>)[^0-9]{0,20}([\d,]{3,12})\s*円/gi;
  for (const m of html.matchAll(re)) {
    const n = Number(m[1].replaceAll(",", ""));
    if (Number.isFinite(n) && n > 0) prices.push(n);
  }
  return prices;
}

/**
 * 中央値。偶数個なら中央2つの平均(小数は切り捨て)。
 *
 * 平均ではなく中央値なのは、相場検索に必ず混ざる極端な出品
 * (1円スタートの取り消し・業者のまとめ売り)に平均が引きずられるため。
 */
export function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) return sorted[mid];
  return Math.floor((sorted[mid - 1] + sorted[mid]) / 2);
}

export interface MarketStats {
  /** 中央値。該当0件なら null */
  medianPrice: number | null;
  /** 母数。0 = 調べたが該当なし(取得失敗とは別物) */
  sampleCount: number;
  query: string;
  sourceUrl: string;
}

/**
 * 落札相場を取得する。ネットワークに出るのはここだけ。
 * 取得自体に失敗したときは投げる(呼び出し側で「0件」と区別するため)。
 */
export async function fetchMarketStats(title: string): Promise<MarketStats> {
  const query = buildMarketQuery(title);
  const sourceUrl = closedSearchUrl(query);
  const res = await fetch(sourceUrl, {
    headers: {
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "ja,en;q=0.8",
    },
  });
  if (!res.ok) throw new Error(`closedsearch fetch failed: HTTP ${res.status}`);
  const prices = parseClosedPrices(await res.text());
  return { medianPrice: median(prices), sampleCount: prices.length, query, sourceUrl };
}
