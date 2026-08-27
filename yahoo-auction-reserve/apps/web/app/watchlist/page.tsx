import { redirect } from "next/navigation";
import { prisma } from "@yar/db";
import { isSeenInLatestSync } from "@yar/shared";
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
      // 連携ごとの最終同期時刻と突き合わせて「今回見えたもの」だけを出す。
      // 連携が複数あるときに他方の同期時刻で判定しないよう、商品ごとに
      // **その商品を取り込んだ連携** の時刻を見る
      include: { yahooSession: { select: { lastWatchlistSyncAt: true } } },
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
  // ⚠️ 同期は upsert しかしない(ヤフオク側から消えた行も残す)。ここで
  // 絞らないと、前の同期の残骸がウォッチ中の商品として並ぶ。
  // 2026-08-28 実測: 本物9件に対し70件表示されていた(shared/watchFreshness.ts)
  const current = items.filter((i) =>
    isSeenInLatestSync({
      lastSeenAt: i.lastSeenAt,
      sessionLastSyncAt: i.yahooSession.lastWatchlistSyncAt,
    }),
  );
  const hiddenStale = items.length - current.length;
  const rows: WatchlistRow[] = current.map((i) => ({
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
        取り込みは Yahoo → アプリの一方向です。ここで非表示にしても、ヤフオク側の
        ウォッチリストは変わりません。
      </p>
      {hiddenStale > 0 && (
        <p className="notice">
          直近の同期で見つからなかった {hiddenStale} 件は表示していません(ヤフオク側で
          ウォッチを外した商品や、取り込みを直す前の古い残骸です)。
        </p>
      )}
      {rows.length === 0 ? (
        <p className="empty">表示できるウォッチ商品がありません。</p>
      ) : (
        <WatchlistRows rows={rows} initialNowMs={Date.now()} />
      )}
    </>
  );
}
