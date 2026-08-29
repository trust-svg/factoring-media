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
      const price = pickNumber(embedded, ["currentPrice", "Price", "price"]);
      if (price !== undefined) info.currentPrice = price;
    }
    if (info.buyNowPrice === undefined) {
      // ⚠️ 2026-08-29 実測: 同じ商品(n1242036522)で **取り出し元によって値が違う**。
      //   埋め込みJSON 8100 / ページ表示テキスト 8910(ちょうど 1.1 倍)
      // JSON が税抜・表示が税込と考えるのが自然で、そうなら買い手が払うのは
      // 8910 のほう。ここは JSON を優先するので、**10% 低い額を出しうる**。
      // 税込側が正だと確認できたら優先順位を入れ替えること。
      // 未確定のまま挙動を変えると、今度は税抜が正しかった商品で 10% 高く出る。
      // 判定材料は p0-probe の「buyNowPrice (表示テキスト)」の行で集める。
      //
      // 即決価格。キー名が揺れるうえ、同名キーが boolean(即決あり/なし)で
      // 先に見つかることがあるので、数値として読める最初の値を採る
      // (pickNumber は数値化できない候補を読み飛ばす)。
      const bin = pickNumber(embedded, [
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
    const sellerBox = pickContainer(embedded, [
      "seller",
      "sellerInfo",
      "sellerModule",
      "Seller",
    ]);
    const seller =
      pickValue(sellerBox, ["displayName", "name", "sellerId", "id"]) ??
      pickValue(embedded, ["sellerId"]);
    if (typeof seller === "string" && seller.trim() !== "") info.sellerName = seller;
  }

  // --- テキストベースのフォールバック ---
  if (info.currentPrice === undefined) {
    const m = html.match(/現在(?:価格)?[^0-9]{0,20}([\d,]+)\s*円/);
    if (m) info.currentPrice = Number(m[1].replaceAll(",", ""));
  }
  if (info.buyNowPrice === undefined) {
    // 「即決価格 12,345円」「即決 12,345 円」の両方を拾う。
    // 「現在価格」の行を巻き込まないよう、数字までの距離を短く取る。
    const m = html.match(/即決(?:価格)?[^0-9]{0,20}([\d,]+)\s*円/);
    if (m) {
      const v = Number(m[1].replaceAll(",", ""));
      if (Number.isFinite(v) && v > 0) info.buyNowPrice = v;
    }
  }
  if (info.hasAutoExtension === undefined) {
    if (/自動延長\s*[:：]?\s*あり/.test(html)) info.hasAutoExtension = true;
    else if (/自動延長\s*[:：]?\s*なし/.test(html)) info.hasAutoExtension = false;
  }
  if (info.isClosed === undefined) {
    info.isClosed = /このオークションは終了しています/.test(html);
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
    if (/送料無料|送料込/.test(html)) info.shippingFee = 0;
    else {
      const m = html.match(/送料[^0-9]{0,20}([\d,]+)\s*円/);
      if (m) info.shippingFee = Number(m[1].replaceAll(",", ""));
      else if (/落札者(?:の)?負担/.test(html)) {
        info.shippingNote = "落札者負担(金額は商品ページを確認)";
      }
    }
  }
  if (info.sellerRating === undefined) {
    const m = html.match(/([\d.]{1,5})\s*%[^0-9]{0,10}(?:good|良い|評価)/i);
    if (m) {
      const v = Number(m[1]);
      if (Number.isFinite(v) && v >= 0 && v <= 100) info.sellerRating = Math.round(v);
    }
  }
  if (info.sellerRatingCount === undefined) {
    const m = html.match(/評価[^0-9]{0,10}([\d,]+)\s*件/);
    if (m) info.sellerRatingCount = Number(m[1].replaceAll(",", ""));
  }

  return info;
}

export async function fetchAuctionInfo(url: string): Promise<AuctionInfo> {
  const html = await fetchAuctionPage(url);
  return parseAuctionPage(html, url);
}

// ---- helpers -------------------------------------------------

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
