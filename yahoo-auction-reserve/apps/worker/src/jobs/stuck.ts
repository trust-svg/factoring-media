import type { Browser } from "playwright";
import { prisma } from "@yar/db";
import { fetchAuctionInfo } from "@yar/shared";
import { notifyUser } from "../notify";
import { launchBrowser, createYahooContext } from "../bidder/session";
import { checkResult } from "../bidder/placeBid";

// 走行中(MONITORING / BIDDING)のまま取り残された予約の掃除。
//
// なぜ要るか: 監視ジョブが落ちる(worker 再起動・OOM・Redis 消失)と、予約は
// 走行中のステータスのまま誰にも拾われなくなる。
//   - scanOnce の再登録対象は SCHEDULED / MONITORING だけ = BIDDING は永久に対象外
//   - runMonitorJob は SCHEDULED / MONITORING 以外なら即 return
//   - refresh は SCHEDULED だけ
// つまり **BIDDING で固まった予約を動かす経路が1つも無い**。しかも入札は
// 送信済みかもしれないので、放置すると「落札しているのに誰も気づかない」に
// なる(取引ナビが立ったまま出品者を待たせる)。
//
// ⚠️ 「終了時刻を過ぎている」だけでは掃除しない。自動延長ループは終了時刻を
// またいで走り続けるので、生きているジョブを横から終わらせてしまう。
// **生きた monitor ジョブが無いこと** を必ず併せて確認する。
export const STUCK_GRACE_MS = 15 * 60 * 1000;

/** 1回の掃除でブラウザを起動する上限。詰まりを一気に処理して資源を食い潰さない */
export const STUCK_MAX_PER_SWEEP = 3;

export interface StuckCandidate {
  id: string;
  status: string;
  endAt: Date;
  hasSuccessfulBid: boolean;
}

/**
 * 掃除対象を選ぶ。
 *
 * @param rows      走行中ステータスの予約
 * @param liveIds   monitor ジョブ(delayed / waiting / active)が残っている予約 ID
 * @param nowMs     現在時刻
 */
export function selectStuck(
  rows: StuckCandidate[],
  liveIds: Set<string>,
  nowMs: number,
): StuckCandidate[] {
  return rows.filter(
    (r) => !liveIds.has(r.id) && nowMs - r.endAt.getTime() >= STUCK_GRACE_MS,
  );
}

/**
 * 結果をヤフオクに見に行く必要があるか。
 *
 * ⚠️ BIDDING は成功した入札記録が無くても見に行く。placeBid が通ったあと
 * BidAttempt を書く前にプロセスが落ちる窓があり、「記録が無い = 入札していない」
 * とは言えない。ここを記録だけで判断すると、落札しているのに LOST どころか
 * 「入札できませんでした」を送ることになる。
 */
export function needsResultCheck(row: { status: string; hasSuccessfulBid: boolean }): boolean {
  return row.status === "BIDDING" || row.hasSuccessfulBid;
}

export async function runStuckSweep(
  liveMonitorIds: Set<string>,
  nowMs: number = Date.now(),
): Promise<number> {
  const rows = await prisma.bidReservation.findMany({
    where: { status: { in: ["MONITORING", "BIDDING"] } },
    include: { attempts: { select: { outcome: true } } },
  });
  const candidates = selectStuck(
    rows.map((r) => ({
      id: r.id,
      status: r.status,
      endAt: r.endAt,
      hasSuccessfulBid: r.attempts.some((a) => a.outcome === "SUCCESS"),
    })),
    liveMonitorIds,
    nowMs,
  );
  if (candidates.length === 0) return 0;

  const byId = new Map(rows.map((r) => [r.id, r]));
  let browser: Browser | undefined;
  let launched = 0;
  let resolved = 0;
  try {
    for (const c of candidates) {
      const reservation = byId.get(c.id);
      if (!reservation) continue;
      console.warn(
        `[stuck] ${reservation.auctionId} (${reservation.id}) が ${reservation.status} のまま` +
          `終了時刻を${Math.round((nowMs - c.endAt.getTime()) / 60000)}分超過。監視ジョブは残っていません`,
      );
      try {
        if (!needsResultCheck(c)) {
          // 入札を送る前に監視が落ちた。落札はありえないので確認は不要。
          // ⚠️ EXPIRED ではなく FAILED。EXPIRED は「上限を超えたので見送った」
          // という判断の結果で、ここは判断すらできなかった故障。同じ状態に
          // 畳むと、監視が落ちている事実がダッシュボードから消える。
          await resolveWithoutCheck(reservation);
          resolved += 1;
          continue;
        }
        if (launched >= STUCK_MAX_PER_SWEEP) {
          // 残りは次の走査へ。取り残しても状態は変わらないので次で拾える。
          console.warn(`[stuck] ${reservation.id} は次の走査へ繰り越し(同時起動の上限)`);
          continue;
        }
        launched += 1;
        browser ??= await launchBrowser();
        await resolveWithCheck(browser, reservation);
        resolved += 1;
      } catch (err) {
        // ⚠️ 例外で抜けたまま走行中ステータスを残さない。残すと次の走査でも
        // 同じ予約を選び、30秒ごとにブラウザを起動し続ける。確認できなかった
        // ことを FAILED として書き切って、人が見る状態にする。
        const detail = err instanceof Error ? err.message : String(err);
        console.error(`[stuck] ${reservation.id} の後始末に失敗:`, detail);
        await markUnverified(reservation, `後始末に失敗しました(${detail})`);
        resolved += 1;
      }
    }
  } finally {
    await browser?.close().catch(() => {});
  }
  return resolved;
}

async function resolveWithoutCheck(reservation: {
  id: string;
  userId: string;
  title: string;
  auctionUrl: string;
  maxBidAmount: number;
}): Promise<void> {
  await prisma.bidReservation.update({
    where: { id: reservation.id },
    data: { status: "FAILED", failureReason: "MONITOR_LOST: 監視が中断されました" },
  });
  await notifyUser(reservation.userId, "FAILED", {
    title: reservation.title,
    url: reservation.auctionUrl,
    reason: "入札の前に監視が中断されたため、入札できませんでした",
    hint: "同じ商品でもう一度予約するか、ヤフオクで直接ご確認ください",
    maxBidAmount: reservation.maxBidAmount,
  });
}

async function resolveWithCheck(
  browser: Browser,
  reservation: {
    id: string;
    userId: string;
    title: string;
    auctionUrl: string;
    maxBidAmount: number;
    yahooSessionId: string;
  },
): Promise<void> {
  const context = await createYahooContext(browser, reservation.yahooSessionId);
  try {
    const page = await context.newPage();
    const { verdict, reason } = await checkResult(page, reservation.auctionUrl);
    const info = await fetchAuctionInfo(reservation.auctionUrl).catch(() => null);
    console.log(`[stuck] ${reservation.id} 結果判定: ${verdict} - ${reason}`);
    if (verdict === "UNKNOWN") {
      // ⚠️ ここでも LOST に畳まない(jobs/monitor.ts と同じ理由)。
      await markUnverified(reservation, reason, info?.currentPrice ?? null);
      return;
    }
    await prisma.bidReservation.update({
      where: { id: reservation.id },
      data: { status: verdict, resultPrice: info?.currentPrice ?? null, failureReason: null },
    });
    await notifyUser(reservation.userId, verdict === "WON" ? "WON" : "LOST", {
      title: reservation.title,
      url: reservation.auctionUrl,
      finalPrice: info?.currentPrice ?? "不明",
      maxBidAmount: reservation.maxBidAmount,
      _lines: ["(監視が中断されていたため、終了後に確認しました)"],
    });
  } finally {
    await context.close().catch(() => {});
  }
}

async function markUnverified(
  reservation: {
    id: string;
    userId: string;
    title: string;
    auctionUrl: string;
    maxBidAmount: number;
  },
  reason: string,
  finalPrice: number | null = null,
): Promise<void> {
  await prisma.bidReservation.update({
    where: { id: reservation.id },
    data: {
      status: "FAILED",
      resultPrice: finalPrice,
      failureReason: `RESULT_UNVERIFIED: ${reason}`,
    },
  });
  await notifyUser(reservation.userId, "FAILED", {
    title: reservation.title,
    url: reservation.auctionUrl,
    reason: `落札できたかどうかを確認できませんでした(${reason})`,
    hint: "ヤフオクの「マイオク > 落札」で結果を確認してください",
    finalPrice: finalPrice ?? "不明",
    maxBidAmount: reservation.maxBidAmount,
  });
}

