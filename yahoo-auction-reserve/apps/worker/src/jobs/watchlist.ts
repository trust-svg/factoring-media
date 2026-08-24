import type { Browser, Page } from "playwright";
import { prisma } from "@yar/db";
import { YAHOO_AUCTION_URL_PATTERN, fetchAuctionInfo } from "@yar/shared";
import { selectors } from "../bidder/selectors";
import { createYahooContext, launchBrowser, markSessionExpired } from "../bidder/session";
import { notifyUser } from "../notify";

// ウォッチリスト同期(ヤフオク → アプリの一方向。設計追補 2026-08-25)。
//
// ⚠️ **ヤフオク側へは書かない**。アプリからウォッチリストを操作すると、
// 入札前の書き込み操作が増えて入札そのものを弾かれるリスクが上がる。
// アプリ側で外した商品は dismissedAt を立てるだけで、ヤフオク側は触らない。
//
// ⚠️ **ヤフオク側から消えた商品をこちらから消さない**。同期が一時的に
// 失敗しただけで候補が消えると、予約しようとしていた商品が黙って無くなる。
// 消えたことは lastSeenAt が古いままになることで表現する。
//
// ⚠️ ウォッチリストはログイン必須なので、**この同期自体がセッションの
// 死活監視を兼ねる**。ログイン画面へ飛ばされたらセッションを EXPIRED にする。

// ⚠️ 未検証: ウォッチリストの URL。`npm run p0:probe -- --watchlist` で確定させること。
// 候補を順に試し、ログイン壁でも商品リンクでもない場合は次を試す。
const WATCHLIST_URL_CANDIDATES = [
  "https://auctions.yahoo.co.jp/user/jp/show/watchlist",
  "https://auctions.yahoo.co.jp/watchlist",
];

export interface WatchlistSyncResult {
  kind: "OK" | "SESSION_EXPIRED" | "UNPARSEABLE";
  itemCount: number;
  detail?: string;
}

export interface ScrapedWatchItem {
  auctionId: string;
  auctionUrl: string;
}

/**
 * 開いたページからウォッチ中の商品を拾う。
 *
 * 「0件」と「読めなかった」を返り値で区別する。ここを一緒にすると、
 * セレクタが変わっただけの日に「ウォッチリストが空になりました」という
 * 正常そうな結果が返り、誰も気づかないまま候補が更新されなくなる。
 */
export async function scrapeWatchlistPage(page: Page): Promise<WatchlistSyncResult & { items: ScrapedWatchItem[] }> {
  if ((await page.locator(selectors.watchlistLoginWall).count()) > 0) {
    return { kind: "SESSION_EXPIRED", itemCount: 0, items: [] };
  }

  // DOM 型(HTMLAnchorElement)は worker の tsconfig(lib: ES only)に無いので、
  // ブラウザ側では getAttribute で取り、絶対 URL 化はこちらで行う。
  const rawHrefs = await page
    .locator(selectors.watchlistItemLink)
    .evaluateAll((els) => els.map((e) => e.getAttribute("href") ?? "").filter(Boolean));
  const pageUrl = page.url();
  const hrefs = rawHrefs.map((h) => {
    try {
      return new URL(h, pageUrl).toString();
    } catch {
      return "";
    }
  });

  const seen = new Set<string>();
  const items: ScrapedWatchItem[] = [];
  for (const href of hrefs) {
    const m = YAHOO_AUCTION_URL_PATTERN.exec(href);
    if (!m?.[1] || seen.has(m[1])) continue;
    seen.add(m[1]);
    items.push({ auctionId: m[1], auctionUrl: href });
  }

  if (items.length === 0) {
    // ログイン壁も商品リンクも無い。本当に空なのか、セレクタが変わったのか
    // ここでは判別できない。**成功として扱わない**(成功にすると
    // lastWatchlistSyncAt が進み、壊れていることが死活監視から消える)。
    return { kind: "UNPARSEABLE", itemCount: 0, items: [], detail: "商品リンクを1件も認識できませんでした" };
  }

  return { kind: "OK", itemCount: items.length, items };
}

export async function runWatchlistSync(yahooSessionId: string): Promise<WatchlistSyncResult> {
  const session = await prisma.yahooSession.findUnique({ where: { id: yahooSessionId } });
  if (!session || session.status !== "ACTIVE") {
    return { kind: "SESSION_EXPIRED", itemCount: 0, detail: "連携が有効ではありません" };
  }

  let browser: Browser | undefined;
  try {
    browser = await launchBrowser();
    const context = await createYahooContext(browser, yahooSessionId);
    const page = await context.newPage();

    let last: (WatchlistSyncResult & { items: ScrapedWatchItem[] }) | null = null;
    for (const url of WATCHLIST_URL_CANDIDATES) {
      await page.goto(url, { waitUntil: "domcontentloaded" });
      last = await scrapeWatchlistPage(page);
      if (last.kind !== "UNPARSEABLE") break; // 壁に当たったか、読めたか
    }
    const result = last ?? { kind: "UNPARSEABLE" as const, itemCount: 0, items: [] };

    if (result.kind === "SESSION_EXPIRED") {
      await markSessionExpired(yahooSessionId);
      await notifyUser(session.userId, "SESSION_EXPIRED", {
        title: `連携「${session.label}」`,
        hint: "ウォッチリストを開いたらログイン画面に飛ばされました。設定画面から再連携してください",
      });
      return { kind: "SESSION_EXPIRED", itemCount: 0 };
    }

    if (result.kind === "UNPARSEABLE") {
      // 既存のウォッチリストには触らない。lastWatchlistSyncAt も進めない。
      console.error(
        `[watchlist] ${session.label}: ページを解釈できませんでした。` +
          "セレクタ(watchlistItemLink)の P0 検証が必要です",
      );
      return result;
    }

    await upsertItems(session.userId, yahooSessionId, result.items);
    await prisma.yahooSession.update({
      where: { id: yahooSessionId },
      data: { lastWatchlistSyncAt: new Date(), lastVerifiedAt: new Date() },
    });
    return { kind: "OK", itemCount: result.itemCount };
  } finally {
    await browser?.close().catch(() => {});
  }
}

async function upsertItems(
  userId: string,
  yahooSessionId: string,
  items: ScrapedWatchItem[],
): Promise<void> {
  for (const item of items) {
    // 商品の詳細は Cookie 無しの HTTP で取れる(実測 2026-08-24: ログイン有無で
    // パーサ結果は同一)。ブラウザを使い回すより軽く、失敗しても同期は続ける。
    const info = await fetchAuctionInfo(item.auctionUrl).catch(() => null);

    await prisma.watchlistItem.upsert({
      where: { userId_auctionId: { userId, auctionId: item.auctionId } },
      create: {
        userId,
        yahooSessionId,
        auctionId: item.auctionId,
        auctionUrl: item.auctionUrl,
        title: info?.title,
        imageUrl: info?.imageUrl,
        currentPrice: info?.currentPrice,
        endAt: info?.endAt,
        hasAutoExtension: info?.hasAutoExtension,
      },
      update: {
        lastSeenAt: new Date(),
        yahooSessionId,
        // 取れなかった項目は既存値を残す。undefined を書き込んで
        // 「一度は取れていた終了時刻」を消さない。
        ...(info?.title !== undefined ? { title: info.title } : {}),
        ...(info?.imageUrl !== undefined ? { imageUrl: info.imageUrl } : {}),
        ...(info?.currentPrice !== undefined ? { currentPrice: info.currentPrice } : {}),
        ...(info?.endAt !== undefined ? { endAt: info.endAt } : {}),
        ...(info?.hasAutoExtension !== undefined
          ? { hasAutoExtension: info.hasAutoExtension }
          : {}),
      },
    });
  }
}

/** ACTIVE な連携すべてを同期する。スケジューラから1時間ごとに呼ぶ */
export async function runWatchlistSweep(): Promise<void> {
  const sessions = await prisma.yahooSession.findMany({
    where: { status: "ACTIVE" },
    select: { id: true, label: true },
  });
  for (const s of sessions) {
    try {
      const r = await runWatchlistSync(s.id);
      console.log(`[watchlist] ${s.label}: ${r.kind} ${r.itemCount}件`);
    } catch (err) {
      // 1件の失敗で他の連携の同期を止めない
      console.error(`[watchlist] ${s.label} の同期に失敗:`, err);
    }
  }
}
