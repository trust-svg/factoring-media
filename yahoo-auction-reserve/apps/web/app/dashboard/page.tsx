import Link from "next/link";
import { redirect } from "next/navigation";
import { prisma } from "@yar/db";
import { RESERVATION_STATUS_LABEL } from "@yar/shared/labels";
import { getSessionUser } from "@/lib/auth";

export const dynamic = "force-dynamic";

function formatRemaining(endAt: Date): string {
  const ms = endAt.getTime() - Date.now();
  if (ms <= 0) return "終了";
  const h = Math.floor(ms / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  if (h >= 24) return `${Math.floor(h / 24)}日${h % 24}時間`;
  return h > 0 ? `${h}時間${m}分` : `${m}分`;
}

export default async function DashboardPage() {
  const user = await getSessionUser();
  if (!user) redirect("/login");

  const reservations = await prisma.bidReservation.findMany({
    where: { userId: user.id },
    orderBy: { endAt: "asc" },
  });

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h1>予約一覧</h1>
        <Link href="/reservations/new">
          <button>新規予約</button>
        </Link>
      </div>
      {reservations.length === 0 && (
        <div className="card">
          <p>
            まだ予約がありません。
            <Link href="/reservations/new">商品URLを貼り付けて予約</Link>
            してみましょう。
          </p>
        </div>
      )}
      {reservations.map((r) => (
        <div className="card" key={r.id}>
          <div className="row">
            {r.imageUrl && (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img className="thumb" src={r.imageUrl} alt="" />
            )}
            <div className="grow">
              <div className="row">
                <span className={`badge ${r.status}`}>
                  {RESERVATION_STATUS_LABEL[r.status]}
                </span>
                {r.hasAutoExtension && <span className="muted">[自動延長あり]</span>}
              </div>
              <Link href={`/reservations/${r.id}`}>
                <strong>{r.title}</strong>
              </Link>
              <p className="muted">
                上限 {r.maxBidAmount.toLocaleString()}円 / 現在価格{" "}
                {r.currentPrice != null ? `${r.currentPrice.toLocaleString()}円` : "—"} /
                終了まで {formatRemaining(r.endAt)}(終了{r.snipeSecondsBefore}秒前に実行)
              </p>
              {r.failureReason && <p className="error">{r.failureReason}</p>}
            </div>
          </div>
        </div>
      ))}
    </>
  );
}
