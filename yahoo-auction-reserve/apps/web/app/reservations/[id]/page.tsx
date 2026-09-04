import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { prisma } from "@yar/db";
import { RESERVATION_STATUS_LABEL, ATTEMPT_OUTCOME_LABEL } from "@yar/shared/labels";
import { judgeBuyNow } from "@yar/shared/judgement";
import { getSessionUser } from "@/lib/auth";
import ReservationActions from "./ReservationActions";

export const dynamic = "force-dynamic";

function fmt(d: Date | null): string {
  return d ? new Date(d).toLocaleString("ja-JP") : "—";
}

export default async function ReservationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const user = await getSessionUser();
  if (!user) redirect("/login");

  const { id } = await params;
  const reservation = await prisma.bidReservation.findUnique({
    where: { id },
    include: {
      attempts: { orderBy: { createdAt: "asc" } },
      yahooSession: { select: { label: true, status: true } },
    },
  });
  // 他人の予約は存在自体を明かさない
  if (!reservation || reservation.userId !== user.id) notFound();

  const executeAt = new Date(
    reservation.endAt.getTime() - reservation.snipeSecondsBefore * 1000,
  );
  const editable = reservation.status === "SCHEDULED";
  // 走行中(監視中・入札中)で、まだ終了していない予約は「上限額の引き上げ」
  // だけできる。入札後に高値更新されたときの追加入札がこの経路。
  const running =
    (reservation.status === "MONITORING" || reservation.status === "BIDDING") &&
    reservation.endAt.getTime() > Date.now();
  const buyNow = judgeBuyNow(reservation.maxBidAmount, reservation.buyNowPrice);

  return (
    <>
      <p className="muted">
        <Link href="/dashboard">← 予約一覧へ</Link>
      </p>

      <div className="card">
        <div className="row">
          {reservation.imageUrl && (
            /* eslint-disable-next-line @next/next/no-img-element */
            <img className="thumb" src={reservation.imageUrl} alt="" />
          )}
          <div className="grow">
            <span className={`badge ${reservation.status}`}>
              {RESERVATION_STATUS_LABEL[reservation.status]}
            </span>
            {reservation.dryRun && (
              <span className="badge dryrun-tag" style={{ marginLeft: 6 }}>
                テスト実行(入札しない)
              </span>
            )}
            {reservation.hasAutoExtension && (
              <span className="muted"> [自動延長あり]</span>
            )}
            <h1 style={{ fontSize: "1.2rem", margin: "8px 0" }}>
              {reservation.title}
            </h1>
            <p className="muted">
              <a href={reservation.auctionUrl} target="_blank" rel="noreferrer">
                ヤフオクで見る({reservation.auctionId})
              </a>
              {reservation.sellerName && ` / 出品者: ${reservation.sellerName}`}
            </p>
          </div>
        </div>
        {reservation.failureReason && (
          <p className="error">失敗理由: {reservation.failureReason}</p>
        )}
      </div>

      <div className="card">
        <h2>予約内容</h2>
        <table>
          <tbody>
            <tr>
              <th style={{ textAlign: "left", paddingRight: 16 }}>上限入札額</th>
              <td>{reservation.maxBidAmount.toLocaleString()}円</td>
            </tr>
            <tr>
              <th style={{ textAlign: "left", paddingRight: 16 }}>入札実行時刻</th>
              <td>
                {fmt(executeAt)}(終了{reservation.snipeSecondsBefore}秒前)
              </td>
            </tr>
            <tr>
              <th style={{ textAlign: "left", paddingRight: 16 }}>終了予定</th>
              <td>
                {fmt(reservation.endAt)}
                {reservation.endAt.getTime() !==
                  reservation.originalEndAt.getTime() &&
                  `(当初 ${fmt(reservation.originalEndAt)} から延長)`}
              </td>
            </tr>
            <tr>
              <th style={{ textAlign: "left", paddingRight: 16 }}>現在価格</th>
              <td>
                {reservation.currentPrice != null
                  ? `${reservation.currentPrice.toLocaleString()}円`
                  : "—"}
                <span className="muted">
                  {" "}
                  (最終確認 {fmt(reservation.priceCheckedAt)})
                </span>
              </td>
            </tr>
            {reservation.buyNowPrice != null && (
              <tr>
                <th style={{ textAlign: "left", paddingRight: 16 }}>即決価格</th>
                <td>
                  {reservation.buyNowPrice.toLocaleString()}円
                  {buyNow.level === "warn" && (
                    <span className="error"> — {buyNow.reasons[0]}</span>
                  )}
                </td>
              </tr>
            )}
            {reservation.resultPrice != null && (
              <tr>
                <th style={{ textAlign: "left", paddingRight: 16 }}>最終価格</th>
                <td>{reservation.resultPrice.toLocaleString()}円</td>
              </tr>
            )}
            <tr>
              <th style={{ textAlign: "left", paddingRight: 16 }}>使用する連携</th>
              <td>
                {reservation.yahooSession.label}
                {reservation.yahooSession.status !== "ACTIVE" && (
                  <span className="error"> (失効中 — 再連携が必要です)</span>
                )}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <ReservationActions
        id={reservation.id}
        editable={editable}
        running={running}
        currentPrice={reservation.currentPrice}
        maxBidAmount={reservation.maxBidAmount}
        snipeSecondsBefore={reservation.snipeSecondsBefore}
        dryRun={reservation.dryRun}
      />

      <div className="card">
        <h2>実行ログ</h2>
        {reservation.attempts.length === 0 && (
          <p className="muted">
            まだ実行されていません。終了{reservation.snipeSecondsBefore}秒前に
            {reservation.dryRun
              ? "自動で起動し、確認画面まで進んで止まります(入札はしません)。"
              : "自動で入札します。"}
          </p>
        )}
        <ol style={{ paddingLeft: 18 }}>
          {reservation.attempts.map((a) => (
            <li key={a.id} style={{ marginBottom: 12 }}>
              <div>
                <span
                  className={`badge ${a.outcome === "SUCCESS" ? "WON" : "FAILED"}`}
                >
                  {ATTEMPT_OUTCOME_LABEL[a.outcome]}
                </span>{" "}
                {a.bidAmount != null && (
                  <strong>{a.bidAmount.toLocaleString()}円</strong>
                )}
              </div>
              <p className="muted" style={{ margin: 0 }}>
                予定 {fmt(a.scheduledFor)} / 実行 {fmt(a.executedAt)}
              </p>
              {a.detail && <p className="error" style={{ margin: 0 }}>{a.detail}</p>}
            </li>
          ))}
        </ol>
      </div>
    </>
  );
}
