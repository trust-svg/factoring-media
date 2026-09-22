"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  formatJstDayLabel,
  formatJstTime,
  formatRemaining,
  formatYen,
  isNearCap,
  isSameJstDay,
  jstDayKey,
  urgencyOf,
} from "@yar/shared/format";
import { judgeBuyNow, judgeMarket, totalWithShipping } from "@yar/shared/judgement";
import { RESERVATION_STATUS_LABEL, type ReservationStatusKey } from "@yar/shared/labels";

export interface ReservationItem {
  id: string;
  title: string;
  imageUrl: string | null;
  endAtMs: number;
  status: ReservationStatusKey;
  currentPrice: number | null;
  buyNowPrice: number | null;
  maxBidAmount: number;
  absoluteMaxAmount: number | null;
  autoRaiseMode: "OFF" | "AUTO" | "APPROVAL";
  snipeSecondsBefore: number;
  hasAutoExtension: boolean;
  failureReason: string | null;
  resultPrice: number | null;
  groupName: string | null;
  shippingFee: number | null;
  sellerRating: number | null;
  marketMedianPrice: number | null;
  marketSampleCount: number | null;
  dryRun: boolean;
}

export type Segment = "active" | "today" | "done";

// ⚠️ ここに新しい終端ステータスを足し忘れると、その予約は「実行待ち」の側に
// 残り続けて一覧の先頭に居座る(終わっているのに終わって見えない)。
const DONE: ReservationStatusKey[] = [
  "WON",
  "LOST",
  "FAILED",
  "CANCELLED",
  "EXPIRED",
  "DRY_RUN",
];
const SEGMENTS: { key: Segment; label: string }[] = [
  { key: "active", label: "すべて" },
  { key: "today", label: "今日" },
  { key: "done", label: "結果" },
];

export default function ReservationList({
  items,
  initialNowMs,
}: {
  items: ReservationItem[];
  initialNowMs: number;
}) {
  // サーバの描画時刻をそのまま初期値にする。ここで Date.now() を使うと
  // サーバとクライアントで別の秒になり、毎回ハイドレーション不一致が出る。
  const [nowMs, setNowMs] = useState(initialNowMs);
  const [segment, setSegment] = useState<Segment>("active");

  useEffect(() => {
    setNowMs(Date.now());
    const t = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const now = new Date(nowMs);
  const { groups, doneItems, todayCount } = useMemo(() => {
    const active = items.filter((r) => !DONE.includes(r.status));
    const done = items
      .filter((r) => DONE.includes(r.status))
      .sort((a, b) => b.endAtMs - a.endAtMs);

    const byDay = new Map<string, ReservationItem[]>();
    for (const r of [...active].sort((a, b) => a.endAtMs - b.endAtMs)) {
      const key = jstDayKey(new Date(r.endAtMs));
      const bucket = byDay.get(key);
      if (bucket) bucket.push(r);
      else byDay.set(key, [r]);
    }
    const todayKey = jstDayKey(now);
    return {
      groups: [...byDay.entries()].map(([key, rows]) => ({ key, rows, isToday: key === todayKey })),
      doneItems: done,
      todayCount: byDay.get(todayKey)?.length ?? 0,
    };
    // 秒ごとの再計算は要らない。日付が変わったときだけ組み直せばよい
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, jstDayKey(now)]);

  const visibleGroups = segment === "today" ? groups.filter((g) => g.isToday) : groups;

  return (
    <>
      <div className="seg" role="tablist" aria-label="表示の絞り込み">
        {SEGMENTS.map((s) => (
          <a
            key={s.key}
            role="tab"
            href={`#${s.key}`}
            aria-current={segment === s.key}
            onClick={(e) => {
              e.preventDefault();
              setSegment(s.key);
            }}
          >
            {s.label}
            {s.key === "today" && todayCount > 0 ? ` ${todayCount}` : ""}
          </a>
        ))}
      </div>

      {segment === "done" ? (
        doneItems.length === 0 ? (
          <p className="empty">終わった予約はまだありません。</p>
        ) : (
          <div className="rows">
            {doneItems.map((r) => (
              <Row key={r.id} r={r} now={now} />
            ))}
          </div>
        )
      ) : visibleGroups.length === 0 ? (
        <p className="empty">
          {segment === "today"
            ? "今日終了する予約はありません。"
            : "予約がありません。"}{" "}
          <Link href="/reservations/new">商品URLから予約する</Link>
        </p>
      ) : (
        visibleGroups.map((g) => (
          <section className={`daygroup${g.isToday ? " today" : ""}`} key={g.key}>
            <header className="daygroup-head">
              <span className="label">
                {g.isToday ? "今日" : formatJstDayLabel(new Date(g.rows[0].endAtMs))}
              </span>
              <span className="count">{g.rows.length}件</span>
              <span className="sum">
                上限計 {formatYen(g.rows.reduce((a, r) => a + r.maxBidAmount, 0))}
              </span>
            </header>
            <div className="rows">
              {g.rows.map((r) => (
                <Row key={r.id} r={r} now={now} />
              ))}
            </div>
          </section>
        ))
      )}
    </>
  );
}

function Row({ r, now }: { r: ReservationItem; now: Date }) {
  const endAt = new Date(r.endAtMs);
  const waiting = r.status === "SCHEDULED" || r.status === "MONITORING";
  const urgency = waiting ? urgencyOf(endAt, now) : "NORMAL";
  const near = isNearCap(r.currentPrice, r.maxBidAmount);

  const cls = ["snipe-row"];
  if (urgency === "TODAY") cls.push("today");
  if (urgency === "URGENT") cls.push("urgent");

  return (
    <Link href={`/reservations/${r.id}`} className={cls.join(" ")}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img className="row-thumb" src={r.imageUrl ?? undefined} alt="" />
      <h3 className="row-title">
        {r.dryRun && (
          <span className="badge dryrun-tag" style={{ marginRight: 6 }}>
            テスト
          </span>
        )}
        {r.title}
      </h3>
      <div className="row-meta">
        <span className="m-price">{r.currentPrice != null ? formatYen(r.currentPrice) : "—"}</span>
        <span className="m-arrow" aria-hidden="true">
          ›
        </span>
        <span
          className={`m-cap${near ? " near" : ""}`}
          title={
            r.autoRaiseMode !== "OFF" && r.absoluteMaxAmount != null
              ? `絶対上限 ${formatYen(r.absoluteMaxAmount)} まで増額`
              : undefined
          }
        >
          {formatYen(r.maxBidAmount)}
          {r.autoRaiseMode !== "OFF" ? "↑" : ""}
        </span>
        <BuyNow r={r} />
        <span className="m-ext">{r.hasAutoExtension ? "延長" : "延長なし"}</span>
        <span className="m-timing">{r.snipeSecondsBefore}秒前</span>
      </div>
      <Clock r={r} endAt={endAt} now={now} waiting={waiting} />
      <span className="row-end">
        {isSameJstDay(endAt, now)
          ? formatJstTime(endAt)
          : `${formatJstDayLabel(endAt)} ${formatJstTime(endAt, false)}`}
      </span>
      <RowNote r={r} />
    </Link>
  );
}

/**
 * 即決価格。
 *
 * ⚠️ **即決価格が無い行でも空の span を描く**。PC 幅では .row-meta が
 * display:contents で固定列グリッドに流し込まれるので、条件付きで要素が
 * 増減すると即決ありの行だけ以降の列が1つずれる(全行を見比べる画面なので
 * ズレは致命的)。
 *
 * 上限額が即決価格以上のときは、ここを警告色にする。3行目の row-note は
 * PC 幅では display:none なので、警告をそこだけに出すと PC で見えない。
 */
function BuyNow({ r }: { r: ReservationItem }) {
  const over = judgeBuyNow(r.maxBidAmount, r.buyNowPrice).level === "warn";
  if (r.buyNowPrice == null) return <span className="m-bin" aria-hidden="true" />;
  return (
    <span
      className={`m-bin${over ? " over" : ""}`}
      title={
        over
          ? "上限額が即決価格以上です。入札した時点で即決成立になります"
          : "即決価格"
      }
    >
      {over ? "⚠ " : ""}即決 {formatYen(r.buyNowPrice)}
    </span>
  );
}

/**
 * 3行目の補足。相場・送料込み総額・グループ・失敗理由をここに集約する。
 *
 * ⚠️ 送料が不明なときに商品代だけを「総額」として出さない。出すと
 * 送料1,500円の商品が最安に見える。不明は不明と書く。
 */
function RowNote({ r }: { r: ReservationItem }) {
  const parts: string[] = [];
  if (r.groupName) parts.push(`[${r.groupName}]`);

  const { total, shippingKnown } = totalWithShipping(r.currentPrice, r.shippingFee);
  if (total != null) parts.push(`総額 ${formatYen(total)}`);
  else if (!shippingKnown && r.currentPrice != null) parts.push("送料不明");

  if (r.marketMedianPrice != null && r.marketSampleCount != null) {
    parts.push(`相場 ${formatYen(r.marketMedianPrice)}(${r.marketSampleCount}件)`);
  }
  const market = judgeMarket(r.maxBidAmount, r.marketMedianPrice, r.marketSampleCount);
  if (market.level === "warn") parts.push(`⚠ ${market.reasons[0]}`);
  // 即決価格以上の上限額は「終了を待たずに落札する」を意味する。
  // 落札は成功として記録されるので、ここに出さないと気付けない。
  const buyNow = judgeBuyNow(r.maxBidAmount, r.buyNowPrice);
  if (buyNow.level === "warn") parts.push(`⚠ ${buyNow.reasons[0]}`);
  if (r.sellerRating != null && r.sellerRating < 95) {
    parts.push(`⚠ 出品者評価 ${r.sellerRating}%`);
  }
  if (r.failureReason) parts.push(r.failureReason);

  return <span className="row-note">{parts.join(" · ")}</span>;
}

/**
 * 残り時間の位置。入札中や決着後は同じ場所が状態表示に変わる。
 * 別の場所に出すと、状態が変わるたびに行の中身が横にずれて読み直しになる。
 */
function Clock({
  r,
  endAt,
  now,
  waiting,
}: {
  r: ReservationItem;
  endAt: Date;
  now: Date;
  waiting: boolean;
}) {
  if (r.status === "BIDDING" || r.status === "MONITORING") {
    return <span className="row-clock state live">{RESERVATION_STATUS_LABEL[r.status]}</span>;
  }
  if (!waiting) {
    // DRY_RUN を "lost" 色にすると「落札ならず」と見分けが付かない。
    // 入札していないのだから勝敗の色は付けない。
    const tone =
      r.status === "WON"
        ? "won"
        : r.status === "FAILED"
          ? "bad"
          : r.status === "DRY_RUN"
            ? "test"
            : "lost";
    return (
      <span className={`row-clock state ${tone}`}>
        {RESERVATION_STATUS_LABEL[r.status]}
        {r.status === "WON" && r.resultPrice != null ? ` ${formatYen(r.resultPrice)}` : ""}
      </span>
    );
  }
  const left = endAt.getTime() - now.getTime();
  if (left <= 0) return <span className="row-clock state live">終了処理中</span>;
  return <span className="row-clock">{formatRemaining(left)}</span>;
}
