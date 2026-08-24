import { redirect } from "next/navigation";
import { prisma } from "@yar/db";
import { formatJstDayLabel, formatJstTime } from "@yar/shared/format";
import { getSessionUser } from "@/lib/auth";
import WatchlistRows, { type WatchlistRow } from "./WatchlistRows";

export const dynamic = "force-dynamic";

/** これ以上同期が止まっていたら、0件表示を「本当に0件」と読まない。 */
const STALE_SYNC_MS = 3 * 60 * 60 * 1000;

export default async function WatchlistPage() {
  const user = await getSessionUser();
  if (!user) redirect("/login");

  const [items, sessions, reservations] = await Promise.all([
    prisma.watchlistItem.findMany({
      where: { userId: user.id, dismissedAt: null },
      orderBy: [{ endAt: "asc" }, { lastSeenAt: "desc" }],
      take: 200,
    }),
    prisma.yahooSession.findMany({
      where: { userId: user.id },
      select: { label: true, status: true, lastWatchlistSyncAt: true },
    }),
    prisma.bidReservation.findMany({
      where: { userId: user.id },
      select: { auctionId: true, status: true },
    }),
  ]);

  const reservedBy = new Map(reservations.map((r) => [r.auctionId, r.status]));
  const rows: WatchlistRow[] = items.map((i) => ({
    id: i.id,
    auctionUrl: i.auctionUrl,
    title: i.title,
    imageUrl: i.imageUrl,
    currentPrice: i.currentPrice,
    endAtMs: i.endAt?.getTime() ?? null,
    hasAutoExtension: i.hasAutoExtension,
    reservedStatus: reservedBy.get(i.auctionId) ?? null,
  }));

  const lastSync = sessions
    .map((s) => s.lastWatchlistSyncAt)
    .filter((d): d is Date => d != null)
    .sort((a, b) => b.getTime() - a.getTime())[0];
  // 同期が止まっているのに一覧が空だと「ウォッチが0件」に見えるが、実際は
  // ログイン切れやセレクタ崩れで読めていない。最終同期時刻を必ず出す。
  const stale = !lastSync || Date.now() - lastSync.getTime() > STALE_SYNC_MS;

  return (
    <>
      <h1>ウォッチリスト</h1>
      <p className={`notice${stale ? " warn" : ""}`}>
        {lastSync
          ? `最終同期 ${formatJstDayLabel(lastSync)} ${formatJstTime(lastSync)}`
          : "まだ一度も同期できていません"}
        {stale &&
          "。ヤフオクのログインが切れているか、ページ構造が変わって読めていない可能性があります(この一覧が0件でも「ウォッチが無い」とは限りません)。"}
        {" "}
        取り込みは Yahoo → アプリの一方向で、アプリ側で伏せてもヤフオク側は変わりません。
      </p>
      {rows.length === 0 ? (
        <p className="empty">表示できるウォッチ商品がありません。</p>
      ) : (
        <WatchlistRows rows={rows} initialNowMs={Date.now()} />
      )}
    </>
  );
}
