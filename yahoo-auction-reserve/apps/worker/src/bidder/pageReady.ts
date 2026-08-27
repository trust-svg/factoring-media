/**
 * ページが「読める状態」になっているかの判定。
 *
 * 2026-08-25 の P0 実測で分かったこと:
 * ヤフオクの新UIはクライアントサイドレンダリング(CSR)。
 * `waitUntil: "domcontentloaded"` の直後に DOM を読むと、React がマウントする前の
 * ほぼ空の ドキュメント を読むことになる。実測ではウォッチリストが 100〜409ms で
 * 「読み込み完了」になり、商品リンク 0件・ログイン壁 0件・クリック要素 3個だった。
 *
 * ⚠️ ここが一番危険なところ: そのとき出るのは **「❌ 全滅」** という、
 * 「セレクタが間違っている」ときと **見分けがつかない** 報告になる。
 * セレクタが正しくても全滅と出るので、プローブが当たりようのない検証になる。
 * だから「描画されていないかもしれない」ことを別の signal として出す。
 *
 * この判定は「セレクタが合っているか」には一切答えない。答えるのは
 * 「そもそも読む価値のある DOM がそこにあるか」だけ。
 */

/**
 * これ未満のクリック要素しか無いページは CSR 未マウントを疑う。
 *
 * 根拠(2026-08-25 実測): 未マウントのウォッチリストは 3個
 * (検索ボタン・PayPayアイコン・検索 input)。描画後の商品ページは 80個超。
 * 5 は「ヘッダとフッターだけの骨組み」を超えたと言える最小ライン。
 */
export const RENDER_MIN_CLICKABLE = 5;

export interface RenderVerdict {
  /** 読む価値のある DOM がありそうか */
  rendered: boolean;
  /** rendered=false のときの理由(レポートにそのまま出す) */
  reason: string;
}

export function renderVerdict(args: {
  clickable: number;
  inputs: number;
}): RenderVerdict {
  const { clickable, inputs } = args;
  if (clickable < RENDER_MIN_CLICKABLE) {
    return {
      rendered: false,
      reason:
        `クリック要素が ${clickable}個しか無い(閾値 ${RENDER_MIN_CLICKABLE})。` +
        `CSR がまだマウントしていない可能性が高い。` +
        `この状態の「❌ 全滅」はセレクタが違う証拠にならない`,
    };
  }
  if (inputs === 0 && clickable < RENDER_MIN_CLICKABLE * 2) {
    return {
      rendered: false,
      reason:
        `input が1つも無く、クリック要素も ${clickable}個と少ない。` +
        `骨組みだけの状態を読んでいる可能性がある`,
    };
  }
  return { rendered: true, reason: "" };
}

export interface LandingVerdict {
  /** 入札フォームに着けたか */
  ok: boolean;
  reason: string;
}

/**
 * 入札ボタンを押した後、本当に入札フォームに着いたかを確かめる。
 *
 * 2026-08-25 の P0 で実際に踏んだ罠:
 * `a[href*='/jp/show/bid']` が入札履歴 `/jp/show/bid_hist` に前方一致して、
 * 「5件」という入札履歴リンクを押してしまった。プローブは
 * 「入札ボタンをクリック ○ 47ms」と **成功として報告した**。
 * 押した先が違うページであることは、その後の全スロット全滅からしか読み取れず、
 * それは上の renderVerdict の症状と区別がつかない。
 *
 * ⚠️ 押す前のセレクタの正しさではなく、**着いた先** で判定する。
 * セレクタが将来ずれても、着地点の判定は生き残る。
 *
 * ⚠️ ただし「入力欄が無い」の判定だけは priceInput の正しさに乗っている。
 * 2026-08-28 の実測では、実際にはモーダルの入札フォームに着いていたのに
 * priceInput が name 属性を当てにした実在しない候補だったため、
 * 「入札フォームに着いていない」と報告した(selectors.ts 地雷11)。
 * だから reason には「セレクタが違う」を **最初に** 残してある。
 * 原因の順番を入れ替えないこと。読む人はここから調べ始める。
 */
export function bidLandingVerdict(args: {
  url: string;
  priceInputCount: number;
}): LandingVerdict {
  const { url, priceInputCount } = args;
  if (/bid_hist/.test(url)) {
    return {
      ok: false,
      reason: `入札履歴ページに着いている(${url})。入札フォームではない`,
    };
  }
  if (priceInputCount === 0) {
    return {
      ok: false,
      reason:
        `入札額の入力欄が1つも無い(${url})。` +
        `セレクタが違うか、入札フォームに着いていないか、まだ描画されていない`,
    };
  }
  return { ok: true, reason: "" };
}

/**
 * 同じページを2回読んで、拾えた件数が一致したかの判定。
 *
 * なぜ要るか(2026-08-26 実測):
 * `/my/watchlist` を20秒差で2回読むと、`a[href*="/jp/auction/"]` が
 * 128件 → 142件(重複除いた商品ID で 64件 → 71件)になった。
 * ウォッチリストが20秒で7件増えることはないので、これは
 * **ウォッチリスト以外のもの(おすすめカルーセル)を拾っている** 証拠。
 *
 * ⚠️ この誤りは「件数が0件」と違って **正常な顔で通る**。
 * scrapeWatchlistPage は OK を返し、同期は成功し、ウォッチしていない商品が
 * 予約候補に並ぶ。数が多いぶん「ちゃんと動いている」ようにすら見える。
 * 件数の一致は、セレクタが**そのページの静的な一覧だけ**を指している
 * ことの必要条件なので、P0 で必ず取る。
 *
 * ⚠️ これは「合っている」ことの証明ではない(たまたま両方とも同じだけ
 * 余計に拾った可能性は消せない)。あくまで **不合格を出すための検査**。
 */
export interface ListStabilityVerdict {
  stable: boolean;
  reason: string;
}

export function listStabilityVerdict(args: {
  first: number;
  second: number;
}): ListStabilityVerdict {
  const { first, second } = args;
  if (first !== second) {
    return {
      stable: false,
      reason:
        `同じページを2回読んで件数が違う(${first}件 → ${second}件)。` +
        "遅延読み込みされる別の一覧(おすすめカルーセル等)を巻き込んでいる",
    };
  }
  if (first === 0) {
    return {
      stable: false,
      reason: "2回とも0件。一致しているが、一覧を指せていないだけの可能性が高い",
    };
  }
  return { stable: true, reason: "" };
}
