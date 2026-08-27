import type { Browser, Page } from "playwright";
import { prisma } from "@yar/db";
import { YAHOO_AUCTION_URL_PATTERN, fetchAuctionInfo } from "@yar/shared";
import { pageIdentityVerdict } from "../bidder/pageIdentity";
import { selectors } from "../bidder/selectors";
import { createYahooContext, launchBrowser, markSessionExpired } from "../bidder/session";
import { settlePage } from "../bidder/settle";
import { CAROUSEL_ANCESTOR_SELECTOR, watchlistScopeVerdict } from "../bidder/watchlistScope";
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
// プローブ(scripts/p0-probe.ts --watchlist)と同じ配列を使う。片方だけ
// 直すと「プローブでは当たったのに本番は別の URL を叩いている」が起きる。
//
// 🪦 2026-08-26 に **存在しないことを確認して外した** URL:
//      https://auctions.yahoo.co.jp/user/jp/show/watchlist
//      https://auctions.yahoo.co.jp/watchlist
//    どちらも「指定されたURLのページは存在しません。」の案内ページが出る。
//    この案内ページはヘッダーとカテゴリ一覧で50個超のリンクを持つため、
//    「描画済み・ログイン壁なし・商品0件」= 空のウォッチリストと区別が
//    付かなかった(詳細は bidder/pageIdentity.ts)。同じ URL を推測で
//    足し直さないこと。**当てずっぽうを増やすのではなく、プローブの
//    「ウォッチリスト導線の探索」でヤフオク自身にリンクを吐かせる。**
export const WATCHLIST_URL_CANDIDATES = [
  // ✅ 2026-08-26 実測で確定。トップページの「ウォッチ」リンクの href そのもの。
  //    タイトルは「Yahoo!オークション - ウォッチ・ほしい物リスト」、HTTP 200。
  //    `/jp/show/mystatus?select=watchlist` もここへリダイレクトされるが、
  //    リダイレクト頼みにせず正規の URL を直接叩く。
  "https://auctions.yahoo.co.jp/my/watchlist",
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
export async function scrapeWatchlistPage(
  page: Page,
  httpStatus: number | null = null,
): Promise<WatchlistSyncResult & { items: ScrapedWatchItem[] }> {
  // ⚠️ 商品リンクを数える **前** に、そもそもウォッチリストに着いているかを見る。
  // 存在しない URL のヤフオク案内ページは商品リンクが0件になるので、
  // 後段の「0件」判定に落ちると「空のウォッチリスト」と区別が付かない。
  const identity = pageIdentityVerdict({
    url: page.url(),
    httpStatus,
    bodyText: await page.locator("body").innerText().catch(() => ""),
  });
  if (identity.kind === "NOT_FOUND") {
    return {
      kind: "UNPARSEABLE",
      itemCount: 0,
      items: [],
      detail: `ウォッチリストの URL が存在しません: ${identity.reason}`,
    };
  }
  if (identity.kind === "LOGIN_REQUIRED") {
    return { kind: "SESSION_EXPIRED", itemCount: 0, items: [] };
  }

  if ((await page.locator(selectors.watchlistLoginWall).count()) > 0) {
    return { kind: "SESSION_EXPIRED", itemCount: 0, items: [] };
  }

  // ⚠️ おすすめカルーセルを除く。同じページに同居していて、素で数えると
  // ウォッチ中9件のところ70件が出る(詳細は bidder/watchlistScope.ts)。
  //
  // DOM 型(HTMLAnchorElement)は worker の tsconfig(lib: ES only)に無いので、
  // ブラウザ側では getAttribute / closest で取り、絶対 URL 化はこちらで行う。
  const allHrefs = await page
    .locator(selectors.watchlistItemLink)
    .evaluateAll((els) => els.map((e) => e.getAttribute("href") ?? "").filter(Boolean));
  const rawHrefs = await page
    .locator(selectors.watchlistItemLink)
    .evaluateAll(
      (els, sel: string) =>
        els
          .filter((e) => e.closest(sel) === null)
          .map((e) => e.getAttribute("href") ?? "")
          .filter(Boolean),
      CAROUSEL_ANCESTOR_SELECTOR,
    );
  const carouselContainers = await page.locator(CAROUSEL_ANCESTOR_SELECTOR).count();

  const scope = watchlistScopeVerdict({
    total: allHrefs.length,
    kept: rawHrefs.length,
    carouselContainers,
  });
  // ⚠️ この3つは毎回出す。クラス名ごと変わって除外が効かなくなった日は、
  // 件数が跳ねること以外に手掛かりが無くなるため(watchlistScope.ts の既知の限界)。
  console.log(
    `[watchlist] 商品リンク ${allHrefs.length}本 → カルーセル除外後 ${rawHrefs.length}本 ` +
      `(カルーセル要素 ${carouselContainers}個)`,
  );
  if (!scope.ok) {
    return {
      kind: "UNPARSEABLE",
      itemCount: 0,
      items: [],
      detail: `ウォッチリストの一覧を切り出せませんでした: ${scope.reason}`,
    };
  }
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
      const res = await page.goto(url, { waitUntil: "domcontentloaded" });
      // ⚠️ ここで待たないと、React がマウントし切る前の DOM を読む。
      // 「読むたびに件数が違う」の原因(bidder/settle.ts)。
      const settled = await settlePage(page);
      if (!settled.verdict.rendered) {
        console.error(
          `[watchlist] ${session.label}: ${url} が描画され切っていません — ${settled.verdict.reason}`,
        );
      }
      last = await scrapeWatchlistPage(page, res?.status() ?? null);
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
      // ⚠️ 理由を決め打ちで書かない。2026-08-26 は実際には
      // 「URL が存在しない」だったのに、この行は「セレクタが外れている」と
      // 断言していて、切り分けを1日ぶん遅らせた。detail を出す。
      console.error(
        `[watchlist] ${session.label}: ウォッチリストを読めませんでした。` +
          `${result.detail ?? "理由不明"} (P0 検証: npm run p0:probe -- --watchlist)`,
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
