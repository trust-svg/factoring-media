// ウォッチリストの一覧だけを拾うためのスコープ判定。
//
// なぜ要るか(2026-08-27 実測):
//   `/my/watchlist` には **本物の一覧と「おすすめ」カルーセルが同居している**。
//   `a[href*="/jp/auction/"]` は両方に当たるので、素で数えると
//   商品IDが 70件 出るが、そのうちウォッチ中なのは **9件だけ**。
//
//   祖先ブロックの内訳(プローブの ancestryReport 実測):
//     65 + 65 本 … gv-Carousel__item < gv-Carousel__items < gv-Carousel__body
//                   < gv-Carousel        ← おすすめカルーセル 65商品(画像とタイトルで2本)
//      9 +  9 本 … gv-Stack < ... < gv-Card(Carousel を通らない)
//                                       ← 本物のウォッチリスト 9商品
//   148本中 130本がカルーセル。ページの input も checkbox が10個
//   (9行 + 全選択)で、9件を裏付けている。
//
// ⚠️ これは **静かに間違う** 種類の不具合だった。件数が増えるほうに壊れるので
//    「同期できている」ようにしか見えず、DB には毎時20〜33件のおすすめ商品が
//    書き込まれ続けて 251件まで膨らんでいた(実物のウォッチは9件)。
//
// ⚠️ 「再読込して件数が一致するか」(listStabilityVerdict)では捕まらない。
//    2026-08-27 の実測では汚染されたまま 70件 → 70件 で **一致した**。
//    描画が落ち着いた後ならカルーセルも安定するため。安定性は
//    不合格を出すための検査であって、合格の根拠にはならない。

/**
 * カルーセルの入れ物。
 *
 * ⚠️ クラス名は `gv-Carousel--<ハッシュ>` のようにビルドごとのハッシュが付く
 *    (実測: `gv-Carousel__button--WaNfn7XeNIprzkgpczEQ`)。
 *    `.gv-Carousel` という完全一致のクラスは **存在しない** ので、
 *    前方一致で見る。`gv-Carousel__item` `gv-Carousel__body` も同時に拾えるが、
 *    どれに当たっても「カルーセルの中」であることに変わりはない。
 */
export const CAROUSEL_ANCESTOR_SELECTOR = '[class*="gv-Carousel"]';

export interface ScopeVerdict {
  /** 拾えた一覧を信用してよいか */
  ok: boolean;
  /** ok=false のときの理由(ログとレポートにそのまま出す) */
  reason: string;
}

/**
 * カルーセルを除いた結果が信用できるかを判定する。
 *
 * ⚠️ この判定が捕まえられ **ない** ケースを明記しておく:
 *    ヤフオクが `gv-Carousel` というクラス名ごと変えた場合、
 *    カルーセル要素数も除外数も両方 0 になり、「カルーセルが無いページ」と
 *    区別が付かない。そのときは混入が黙って戻る。
 *    **だから同期ログには毎回 total/kept/カルーセル数の3つを出す** —
 *    件数が跳ねたときに、原因をログだけで割れるようにしておくため。
 *    独立した裏取り(行のチェックボックス数など)は、行のDOM構造を
 *    実測してからにする。推測で足すと、また落ちようのない検査が増える。
 */
export function watchlistScopeVerdict(args: {
  /** 除外前の商品リンク数 */
  total: number;
  /** カルーセルの外にあった商品リンク数 */
  kept: number;
  /** ページ上のカルーセル要素の数 */
  carouselContainers: number;
}): ScopeVerdict {
  const { total, kept, carouselContainers } = args;

  if (total > 0 && carouselContainers > 0 && kept === total) {
    return {
      ok: false,
      reason:
        `カルーセルがページ上に ${carouselContainers}個あるのに、` +
        `商品リンク ${total}本を1本も除外していない。` +
        `除外条件(${CAROUSEL_ANCESTOR_SELECTOR})が効いていない`,
    };
  }

  if (total > 0 && kept === 0) {
    return {
      ok: false,
      reason:
        `商品リンク ${total}本が全部カルーセルの中だった。` +
        `一覧側の DOM が変わって、ウォッチ中の商品を拾えていない可能性がある`,
    };
  }

  return { ok: true, reason: "" };
}
