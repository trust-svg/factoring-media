"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { formatJstDayLabel, formatJstTime, formatRemaining, formatYen } from "@yar/shared/format";

export interface WatchlistRow {
  id: string;
  auctionUrl: string;
  title: string | null;
  imageUrl: string | null;
  currentPrice: number | null;
  endAtMs: number | null;
  hasAutoExtension: boolean | null;
  reservedStatus: string | null;
}

export default function WatchlistRows({
  rows,
  initialNowMs,
}: {
  rows: WatchlistRow[];
  initialNowMs: number;
}) {
  const router = useRouter();
  const [nowMs, setNowMs] = useState(initialNowMs);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    setNowMs(Date.now());
    const t = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const dismiss = async (id: string) => {
    setBusy(id);
    try {
      await fetch(`/api/v1/watchlist/${id}`, { method: "DELETE" });
      router.refresh();
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="rows">
      {rows.map((r) => {
        const endAt = r.endAtMs != null ? new Date(r.endAtMs) : null;
        const left = endAt ? endAt.getTime() - nowMs : null;
        return (
          <article className={`wl-row${r.reservedStatus ? " dim" : ""}`} key={r.id}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={r.imageUrl ?? undefined} alt="" />
            <div className="wl-body">
              <a className="wl-title" href={r.auctionUrl} target="_blank" rel="noreferrer">
                {r.title ?? r.auctionUrl}
              </a>
              <div className="wl-meta">
                {r.currentPrice != null ? formatYen(r.currentPrice) : "—"}
                {endAt && (
                  <>
                    {" · "}
                    {formatJstDayLabel(endAt)} {formatJstTime(endAt, false)}
                    {left != null && ` · 残り ${formatRemaining(left)}`}
                  </>
                )}
                {r.hasAutoExtension ? " · 延長" : ""}
              </div>
            </div>
            <div className="wl-actions">
              {r.reservedStatus ? (
                <span className="muted">予約済み</span>
              ) : (
                <>
                  <Link href={`/reservations/new?url=${encodeURIComponent(r.auctionUrl)}`}>
                    <button>予約する</button>
                  </Link>
                  <button
                    className="secondary"
                    disabled={busy === r.id}
                    onClick={() => dismiss(r.id)}
                  >
                    伏せる
                  </button>
                </>
              )}
            </div>
          </article>
        );
      })}
    </div>
  );
}
