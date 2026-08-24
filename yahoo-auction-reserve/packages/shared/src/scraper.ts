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
      const price = pickNumber(embedded, ["price", "currentPrice", "Price"]);
      if (price !== undefined) info.currentPrice = price;
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
    const seller = pickValue(embedded, ["sellerId", "displayName"]);
    if (typeof seller === "string") info.sellerName = seller;
  }

  // --- テキストベースのフォールバック ---
  if (info.currentPrice === undefined) {
    const m = html.match(/現在(?:価格)?[^0-9]{0,20}([\d,]+)\s*円/);
    if (m) info.currentPrice = Number(m[1].replaceAll(",", ""));
  }
  if (info.hasAutoExtension === undefined) {
    if (/自動延長\s*[:：]?\s*あり/.test(html)) info.hasAutoExtension = true;
    else if (/自動延長\s*[:：]?\s*なし/.test(html)) info.hasAutoExtension = false;
  }
  if (info.isClosed === undefined) {
    info.isClosed = /このオークションは終了しています/.test(html);
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

// ネストしたオブジェクトからキー名の一致で最初の値を探す(構造変更に強くするため)
function pickValue(obj: unknown, keys: string[]): unknown {
  const seen = new Set<unknown>();
  const stack: unknown[] = [obj];
  while (stack.length > 0) {
    const cur = stack.pop();
    if (cur === null || typeof cur !== "object" || seen.has(cur)) continue;
    seen.add(cur);
    for (const [k, v] of Object.entries(cur as Record<string, unknown>)) {
      if (keys.includes(k) && v !== null && v !== undefined) return v;
      if (typeof v === "object") stack.push(v);
    }
  }
  return undefined;
}

function pickNumber(obj: unknown, keys: string[]): number | undefined {
  const v = pickValue(obj, keys);
  if (typeof v === "number") return v;
  if (typeof v === "string") {
    const n = Number(v.replaceAll(",", ""));
    if (Number.isFinite(n)) return n;
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
