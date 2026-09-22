import * as cheerio from "cheerio";
import { YAHOO_AUCTION_URL_PATTERN } from "./constants";
import type { AuctionInfo } from "./types";

// =============================================================
// ヤフオク商品ページのパーサ
//
// ※ セレクタ・正規表現は 2026-08 時点の想定であり、P0 検証(設計 §13)で
//   実ページに対して必ず突き合わせること。ヤフオク側のUI変更に備えて
//   「複数の戦略を順に試し、取れた項目だけ返す」構造にしてある。
// =============================================================

export function extractAuctionId(url: string): string | null {
  const m = url.match(YAHOO_AUCTION_URL_PATTERN);
  return m ? m[1] : null;
}

export function normalizeAuctionUrl(auctionId: string): string {
  return `https://page.auctions.yahoo.co.jp/jp/auction/${auctionId}`;
}

export async function fetchAuctionPage(url: string): Promise<string> {
  const res = await fetch(url, {
    headers: {
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "ja,en;q=0.8",
    },
    redirect: "follow",
  });
  if (!res.ok) {
    throw new Error(`Auction page fetch failed: HTTP ${res.status}`);
  }
  return await res.text();
}

export function parseAuctionPage(html: string, url: string): AuctionInfo {
  const auctionId = extractAuctionId(url) ?? "unknown";
  const $ = cheerio.load(html);
  const info: AuctionInfo = { auctionId, url };

  // --- タイトル / 画像: OGP は UI 変更に強いので第一候補 ---
  info.title =
    $('meta[property="og:title"]').attr("content")?.trim() ||
    $("title").text().trim() ||
    undefined;
  info.imageUrl = $('meta[property="og:image"]').attr("content") || undefined;

  // --- ページ内埋め込みJSON(pageData / __NEXT_DATA__ 相当)からの抽出 ---
  const embedded = extractEmbeddedJson(html);
  if (embedded) {
    if (info.currentPrice === undefined) {
      // 具体的なキーを先に置く。優先順位が実際に効くようになったので、
      // 汎用的な `price`(送料・関連商品などにも付く)を先頭にすると
      // そちらが勝ってしまう。
      //
      // ⚠️ 即決価格と違い、ここは **税込(taxinPrice)に寄せていない**。
      // 現在価格は minimumBidToBeat 経由で **入札額の計算**に使うので、
      // 入札欄と同じ物差しでなければならない。入札欄が税抜か税込かは
      // 未測定(2026-08-29 に測った n1242036522 は price も taxinPrice も 1 で
      // 区別が付かなかった)。物差しを間違えると入札額が 10% ずれるので、
      // ストア出品(price ≠ taxinPrice)で `--stage2` を回し、
      // 入札フォームの最低入札価格と突き合わせてから変えること。
      const price = pickNumber(embedded, ["currentPrice", "Price", "price"]);
      if (price !== undefined) info.currentPrice = price;
    }
    if (info.buyNowPrice === undefined) {
      // ⚠️ **税込を先に採る**。2026-08-29 に実ページの埋め込みJSONで確定:
      //   ストア出品 n1242036522: bidOrBuyPrice 8100 / taxRate 10 /
      //                           taxinBidorbuy 8910、表示は「即決 8,910円(税込)」
      //   個人出品   o1242306599: 税キーそのものが無く、表示は「即決 44,000円(税0円)」
      // つまり bidOrBuyPrice は **税抜**で、買い手が払うのは taxin 側。
      // 個人出品は税0なので両者は一致する。
      //
      // 税抜(小さいほう)を出すと、支払額を 10% 低く見せることになる。
      // 逆に税込にすると judgeBuyNow の「上限額が即決価格以上」の警告が
      // 鳴らない帯(8100〜8910)ができるが、その帯で即決が成立しても
      // **支払額は必ず本人の上限以下**なので、金銭的な損は出ない
      // (驚きは出る)。表示額の誤りのほうが実害が大きいので税込を採る。
      //
      // 即決価格。キー名が揺れるうえ、同名キーが boolean(即決あり/なし)で
      // 先に見つかることがあるので、数値として読める最初の値を採る
      // (pickNumber は数値化できない候補を読み飛ばす)。
      const bin = pickNumber(embedded, [
        "taxinBidorbuy",
        "taxinBidOrBuyPrice",
        "bidOrBuyPrice",
        "bidorbuyPrice",
        "bidorbuy_price",
        "Bidorbuy",
        "bidorbuy",
        "buyNowPrice",
        "buyPrice",
      ]);
      // 0 は「即決なし」を 0 で表す実装があるため採らない(0円即決に見える)。
      if (bin !== undefined && bin > 0) info.buyNowPrice = bin;
    }
    // 入札件数。2026-08-29 実測でヤフオクの埋め込みJSONに `bids` として入って
    // いることを確認した(o1242306599 で 10件、p1241285646 で 0件)。
    // `biddersNum`(入札した人数)とは別物なので混ぜない。同じ商品で
    // bids 10 / biddersNum 8 だった。
    const bids = pickNumber(embedded, ["bids", "bidCount", "bidsCount"]);
    if (bids !== undefined && bids >= 0) info.bidCount = bids;
    const endTime = pickValue(embedded, ["endTime", "endtime", "EndTime"]);
    if (typeof endTime === "string" || typeof endTime === "number") {
      const d = parseYahooDate(endTime);
      if (d) info.endAt = d;
    }
    const autoExt = pickValue(embedded, ["isAutomaticExtension", "autoExtension"]);
    if (typeof autoExt === "boolean") info.hasAutoExtension = autoExt;
    const closed = pickValue(embedded, ["isClosed", "closed"]);
    if (typeof closed === "boolean") info.isClosed = closed;
    // ⚠️ 出品者名を木全体から `displayName` で拾わないこと。
    // 2026-08-29 実測(n1242036522・入札後の商品ページ): ログイン中の自分の
    // 表示名「Royal Coin Japan」が出品者名として入っていた(正しくは
    // 「ReRe オークションストア」)。`displayName` はキー名だけでは
    // 持ち主が決まらないので、まず出品者の入れ物まで降りてから探す。
    //
    // 入れ物が見つからなければ `sellerId`(ID なので持ち主が曖昧にならない)
    // だけを見て、それも無ければ **undefined のままにする**。
    // 「誰かの名前が入っている」より「空」のほうが安全で、
    // 出品者を見て入札を止める判断が他人の名前で下されることを防ぐ。
    const seller = pickSellerName(embedded, auctionId);
    if (seller !== undefined) info.sellerName = seller;
  }

  // --- テキストベースのフォールバック ---
  //
  // ⚠️ **生HTMLに当ててはいけない**。ヤフオクの商品ページはこう出る:
  //   即決</dt><dd class="sc-1f0603b0-1 eNGAca"><span class="sc-1f0603b0-3 ...">44,000<!-- -->円
  // ラベルと数字の間に 90 文字以上のタグが挟まり、しかも **クラス名に数字が
  // 入っている**(sc-1f0603b0-1)。下の正規表現はどれも「間に数字が無いこと」を
  // 要求するので、生HTMLに対しては構造上ぜったいに当たらない。
  // 2026-08-29 に実ページ3件で確認: 表示テキスト側が全件「見つからず」だった。
  //
  // 埋め込みJSONが取れている間は誰も気づかない。しかも同じ日に、
  // プレーン fetch の SSR JSON には bidOrBuyPrice が **無い**ことも分かった
  // (ブラウザで描画した DOM には有る)。つまりこのフォールバックが必要になる
  // 場面は実在していて、そこで黙って空を返していた。
  //
  // ⚠️ ただしこのフォールバックは **ページ全体**を1本の文字列として見るので、
  // 「見た目が似ている商品」「今すぐ落札できる商品」などのカルーセルに並ぶ
  // **別出品の価格**を拾いうる。2026-08-29 の終了済みページ(n1242036522)では
  // 本文より先にカルーセルの「現在 1円」「即決 21,000円」が現れていた
  // (実際の即決は 8,910円)。埋め込みJSONが取れている限りここには来ないが、
  // 来たときは他人の値を自信満々に返す形になっている。
  // 値を **JSON から取れなかった時点で怪しい**ので、フォールバックが効いた
  // ことは呼び側に分かるようにしたい(未実装。地雷として残す)。
  const text = stripTags(html);
  if (info.currentPrice === undefined) {
    const m = text.match(/現在(?:価格)?[^0-9]{0,20}([\d,]+)\s*円/);
    if (m) info.currentPrice = Number(m[1].replaceAll(",", ""));
  }
  if (info.buyNowPrice === undefined) {
    // 「即決価格 12,345円」「即決 12,345 円」の両方を拾う。
    // 「現在価格」の行を巻き込まないよう、数字までの距離を短く取る。
    const m = text.match(/即決(?:価格)?[^0-9]{0,20}([\d,]+)\s*円/);
    if (m) {
      const v = Number(m[1].replaceAll(",", ""));
      if (Number.isFinite(v) && v > 0) info.buyNowPrice = v;
    }
  }
  if (info.hasAutoExtension === undefined) {
    if (/自動延長\s*[:：]?\s*あり/.test(text)) info.hasAutoExtension = true;
    else if (/自動延長\s*[:：]?\s*なし/.test(text)) info.hasAutoExtension = false;
  }
  if (info.isClosed === undefined) {
    info.isClosed = /このオークションは終了しています/.test(text);
  }

  // --- 判断材料(送料・出品者評価) ---
  // ⚠️ ここも未検証のプレースホルダ。取れなければ undefined のままにして、
  //    「0円」「評価100%」のような都合の良い既定値を作らないこと。
  //    既定値を入れると、パーサが壊れた日から全商品が足切りを素通りする。
  if (embedded) {
    const fee = pickNumber(embedded, ["shippingFee", "postage", "shipping"]);
    if (fee !== undefined && fee >= 0) info.shippingFee = fee;
    const rating = pickNumber(embedded, ["goodRating", "ratingScore", "sellerRating"]);
    if (rating !== undefined && rating >= 0 && rating <= 100) info.sellerRating = rating;
    const count = pickNumber(embedded, ["totalRating", "ratingCount", "sellerRatingCount"]);
    if (count !== undefined && count >= 0) info.sellerRatingCount = count;
  }
  if (info.shippingFee === undefined) {
    if (/送料無料|送料込/.test(text)) info.shippingFee = 0;
    else {
      const m = text.match(/送料[^0-9]{0,20}([\d,]+)\s*円/);
      if (m) info.shippingFee = Number(m[1].replaceAll(",", ""));
      else if (/落札者(?:の)?負担/.test(text)) {
        info.shippingNote = "落札者負担(金額は商品ページを確認)";
      }
    }
  }
  if (info.sellerRating === undefined) {
    const m = text.match(/([\d.]{1,5})\s*%[^0-9]{0,10}(?:good|良い|評価)/i);
    if (m) {
      const v = Number(m[1]);
      if (Number.isFinite(v) && v >= 0 && v <= 100) info.sellerRating = Math.round(v);
    }
  }
  if (info.sellerRatingCount === undefined) {
    const m = text.match(/評価[^0-9]{0,10}([\d,]+)\s*件/);
    if (m) info.sellerRatingCount = Number(m[1].replaceAll(",", ""));
  }

  return info;
}

export async function fetchAuctionInfo(url: string): Promise<AuctionInfo> {
  const html = await fetchAuctionPage(url);
  return parseAuctionPage(html, url);
}

// ---- helpers -------------------------------------------------

// タグを落として「人が読む文字」だけにする。テキストのフォールバックは
// 必ずこれを通してから当てる(理由は parseAuctionPage 内のコメント)。
//
// script/style を先に消すのは、埋め込みJSONの中身が本文に混ざるのを防ぐため
// (`"price":510` のような文字列が数値の正規表現に拾われうる)。
function stripTags(html: string): string {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/\s+/g, " ");
}

function extractEmbeddedJson(html: string): unknown | null {
  // 1) __NEXT_DATA__
  const next = html.match(
    /<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/,
  );
  if (next) {
    try {
      return JSON.parse(next[1]);
    } catch {
      /* fallthrough */
    }
  }
  // 2) var pageData = {...};
  const legacy = html.match(/var\s+pageData\s*=\s*(\{[\s\S]*?\});/);
  if (legacy) {
    try {
      return JSON.parse(legacy[1]);
    } catch {
      /* fallthrough */
    }
  }
  return null;
}

// ネストしたオブジェクトからキー名が一致する値を探す(構造変更に強くするため)。
// 見つかった順に **すべて** 返す。1件目で打ち切ると、同じキー名が別の型で
// 先に現れたときに後続の使える値まで捨てることになる(即決価格は
// boolean の「即決あり/なし」と同名で入っている実装がある)。
//
// ⚠️ 並びは **キー配列の優先順位が先、木の探索順は後**。
// 2026-08-29 まではキー配列を `includes` で「どれか一致」として扱っていたので、
// 呼び出し側が優先順位のつもりで並べたキーが効いておらず、**たまたま探索で
// 先に当たったキー**が勝っていた(探索は stack.pop() の深さ優先なので、
// 文書順ですらない)。実害として、入札後の商品ページで
// `pickValue(embedded, ["sellerId", "displayName"])` が
// **ログイン中の自分の表示名**を出品者名として返した。
// キー配列は優先順位である、を実装に一致させる。
function pickAll(obj: unknown, keys: string[]): unknown[] {
  const byKey = new Map<string, unknown[]>(keys.map((k) => [k, []]));
  const seen = new Set<unknown>();
  const stack: unknown[] = [obj];
  while (stack.length > 0) {
    const cur = stack.pop();
    if (cur === null || typeof cur !== "object" || seen.has(cur)) continue;
    seen.add(cur);
    for (const [k, v] of Object.entries(cur as Record<string, unknown>)) {
      if (v !== null && v !== undefined) byKey.get(k)?.push(v);
      if (typeof v === "object") stack.push(v);
    }
  }
  return keys.flatMap((k) => byKey.get(k) ?? []);
}

function pickValue(obj: unknown, keys: string[]): unknown {
  return pickAll(obj, keys)[0];
}

// キー名が containerKeys のいずれかに一致する **入れ物** を探して返す。
// 「出品者の表示名」のように、キー名だけでは持ち主が決まらない値のために使う。
// 木全体から `displayName` を拾うと買い手(自分)の名前も候補に入るので、
// まず出品者の入れ物まで降りてから探す。
function pickContainer(obj: unknown, containerKeys: string[]): unknown {
  return pickAll(obj, containerKeys).find(
    (v) => v !== null && typeof v === "object",
  );
}

const SELLER_CONTAINER_KEYS = ["seller", "sellerInfo", "sellerModule", "Seller"];
const SELLER_NAME_KEYS = ["displayName", "name", "sellerId", "id"];
const AUCTION_ID_KEYS = ["auctionId", "auctionID", "aID", "aid"];

/**
 * 伏字化された ID(`buo********`)かどうか。
 *
 * ⚠️ ヤフオクが伏せるのは **入札者**の ID。出品者は評価ページへのリンクに
 * ID がそのまま出るので伏字にならない。つまり伏字が出品者名として
 * 取れたということは、**入札者の入れ物を掴んでいる**という証拠であって、
 * 「伏字の出品者」ではない。実際に保存されている壊れた値がこの形
 * (`buo********` / `piz********`)。
 */
export function isMaskedYahooId(v: string): boolean {
  return /\*{2,}/.test(v);
}

/** 対象オークションの id を持つオブジェクトを、木の中から全部集める */
function objectsForAuction(obj: unknown, auctionId: string): unknown[] {
  const hits: unknown[] = [];
  const seen = new Set<unknown>();
  const stack: unknown[] = [obj];
  while (stack.length > 0) {
    const cur = stack.pop();
    if (cur === null || typeof cur !== "object" || seen.has(cur)) continue;
    seen.add(cur);
    const entries = Object.entries(cur as Record<string, unknown>);
    if (entries.some(([k, v]) => AUCTION_ID_KEYS.includes(k) && v === auctionId)) {
      hits.push(cur);
    }
    for (const [, v] of entries) if (typeof v === "object") stack.push(v);
  }
  return hits;
}

/**
 * 出品者名を取る。
 *
 * ⚠️ 木全体から最初に見つかった `seller` を採ってはいけない。商品ページには
 * **おすすめ・関連商品など他の出品者の入れ物が同居**しており、探索は
 * stack.pop() の深さ優先なので文書順ですらない。どれが勝つかは実質偶然で、
 * 「たまたま先に当たった他人」が出品者として保存される(実害の記録は
 * 上の parseAuctionPage 内コメントと、DB に残った伏字の値)。
 *
 * そこで **対象オークションの id を持つ入れ物の中を先に見る**。
 * 見つからなければ木全体に落ちるが、伏字(入札者の印)は最後まで採らない。
 * どれも駄目なら **undefined のまま返す**。他人の名前で「この出品者だから
 * 入札する/しない」を判断されるより、空のほうが安全。
 */
export function pickSellerName(embedded: unknown, auctionId: string): string | undefined {
  const scopes = [...objectsForAuction(embedded, auctionId), embedded];
  for (const scope of scopes) {
    const box = pickContainer(scope, SELLER_CONTAINER_KEYS);
    // ⚠️ 入れ物の中も **候補を全部** 見る。先頭(displayName)が伏字だからと
    // いって入れ物ごと捨てると、同じ入れ物に入っている使える名前まで
    // 落ちる(この形はテストで踏んだ)。
    for (const v of pickAll(box, SELLER_NAME_KEYS)) {
      if (typeof v === "string" && v.trim() !== "" && !isMaskedYahooId(v)) return v.trim();
    }
  }
  const id = pickValue(embedded, ["sellerId"]);
  if (typeof id === "string" && id.trim() !== "" && !isMaskedYahooId(id)) return id.trim();
  return undefined;
}

/**
 * 出品者名の候補を **採用順に全部** 返す(P0 プローブの証拠取り用)。
 * 「どれを採ったか」ではなく「何と何が候補に居たか」を見るためのもので、
 * 実ページの構造を推測せずに確かめるために使う。
 */
export function sellerNameCandidates(
  html: string,
  url: string,
): { scope: string; key: string; value: string; masked: boolean }[] {
  const embedded = extractEmbeddedJson(html);
  if (!embedded) return [];
  const auctionId = extractAuctionId(url) ?? "unknown";
  const out: { scope: string; key: string; value: string; masked: boolean }[] = [];
  const anchored = objectsForAuction(embedded, auctionId);
  const scopes: [string, unknown][] = [
    ...anchored.map((o, i): [string, unknown] => [`auctionId一致#${i + 1}`, o]),
    ["木全体", embedded],
  ];
  for (const [label, scope] of scopes) {
    const box = pickContainer(scope, SELLER_CONTAINER_KEYS);
    if (box === undefined) continue;
    for (const key of SELLER_NAME_KEYS) {
      for (const v of pickAll(box, [key])) {
        if (typeof v === "string" && v.trim() !== "") {
          out.push({ scope: label, key, value: v.trim(), masked: isMaskedYahooId(v) });
        }
      }
    }
  }
  for (const v of pickAll(embedded, ["sellerId"])) {
    if (typeof v === "string" && v.trim() !== "") {
      out.push({ scope: "木全体(sellerIdのみ)", key: "sellerId", value: v.trim(), masked: isMaskedYahooId(v) });
    }
  }
  return out;
}

function toNumber(v: unknown): number | undefined {
  if (typeof v === "number") return Number.isFinite(v) ? v : undefined;
  if (typeof v === "string") {
    const n = Number(v.replaceAll(",", ""));
    if (Number.isFinite(n) && v.trim() !== "") return n;
  }
  return undefined;
}

/** 数値として読める最初の候補を返す。読めない候補(boolean・オブジェクト)は飛ばす */
function pickNumber(obj: unknown, keys: string[]): number | undefined {
  for (const v of pickAll(obj, keys)) {
    const n = toNumber(v);
    if (n !== undefined) return n;
  }
  return undefined;
}

function parseYahooDate(v: string | number): Date | null {
  if (typeof v === "number") {
    // epoch 秒/ミリ秒の両対応
    const ms = v > 1e12 ? v : v * 1000;
    return new Date(ms);
  }
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? null : d;
}
