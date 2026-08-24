// 予約前の判断材料(出品者の足切り・相場との乖離・送料込み総額)。
// すべて純粋関数。DB もネットワークも触らないのでそのままテストできる。

export interface SellerFacts {
  sellerRating: number | null; // 良い評価の割合(%)
  sellerRatingCount: number | null; // 評価総数
}

export interface SellerThresholds {
  sellerRatingFloor: number | null;
  sellerRatingMinCount: number | null;
}

export type JudgementLevel = "ok" | "warn" | "unknown";

export interface Judgement {
  level: JudgementLevel;
  reasons: string[];
}

/**
 * 出品者の足切り判定。
 *
 * ⚠️ **取得できていない(null)を「合格」に丸めない**。
 * 評価が読めなかった商品を ok にすると、パーサが壊れた日から
 * 全商品が黙って足切りを通過する。判断できないことは unknown として
 * 画面にそう出す(ブロック設定があっても止めるのは warn のときだけ)。
 */
export function judgeSeller(facts: SellerFacts, th: SellerThresholds): Judgement {
  const noThresholds = th.sellerRatingFloor == null && th.sellerRatingMinCount == null;
  if (noThresholds) return { level: "ok", reasons: [] };

  const reasons: string[] = [];
  let unknown = false;

  if (th.sellerRatingFloor != null) {
    if (facts.sellerRating == null) unknown = true;
    else if (facts.sellerRating < th.sellerRatingFloor) {
      reasons.push(
        `出品者の良い評価が${facts.sellerRating}%(下限${th.sellerRatingFloor}%)`,
      );
    }
  }
  if (th.sellerRatingMinCount != null) {
    if (facts.sellerRatingCount == null) unknown = true;
    else if (facts.sellerRatingCount < th.sellerRatingMinCount) {
      reasons.push(
        `評価が${facts.sellerRatingCount}件しかありません(下限${th.sellerRatingMinCount}件)`,
      );
    }
  }

  if (reasons.length > 0) return { level: "warn", reasons };
  if (unknown) return { level: "unknown", reasons: ["出品者の評価を取得できませんでした"] };
  return { level: "ok", reasons: [] };
}

/** 相場からこの倍率以上に高い上限額は警告する。 */
export const MARKET_WARN_RATIO = 1.2;

/**
 * 相場との比較。母数が少ないうちは中央値が当てにならないので判定しない。
 * (1件だけの落札を「相場」と呼ぶと、その1件の異常値で毎回警告が出る)
 */
export const MARKET_MIN_SAMPLES = 3;

export function judgeMarket(
  maxBidAmount: number,
  marketMedianPrice: number | null,
  marketSampleCount: number | null,
): Judgement {
  if (marketMedianPrice == null || marketSampleCount == null) {
    return { level: "unknown", reasons: [] };
  }
  if (marketSampleCount < MARKET_MIN_SAMPLES) {
    return {
      level: "unknown",
      reasons: [`落札実績が${marketSampleCount}件しかなく相場を判断できません`],
    };
  }
  if (maxBidAmount > marketMedianPrice * MARKET_WARN_RATIO) {
    const pct = Math.round((maxBidAmount / marketMedianPrice - 1) * 100);
    return {
      level: "warn",
      reasons: [`上限額が落札相場(中央値${marketMedianPrice}円)より${pct}%高い`],
    };
  }
  return { level: "ok", reasons: [] };
}

/**
 * 送料込みの総額。
 *
 * ⚠️ **送料不明(null)を 0 として足さない**。足すと「総額」の顔をした
 * 商品代だけの数字が出て、相場比較も足切りもその数字で行われる。
 */
export function totalWithShipping(
  price: number | null,
  shippingFee: number | null,
): { total: number | null; shippingKnown: boolean } {
  if (price == null) return { total: null, shippingKnown: shippingFee != null };
  if (shippingFee == null) return { total: null, shippingKnown: false };
  return { total: price + shippingFee, shippingKnown: true };
}
