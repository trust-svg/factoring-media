import type { Job } from "bullmq";
import type { Browser, BrowserContext, Page } from "playwright";
import { prisma, type BidReservation } from "@yar/db";
import {
  EXTENSION_LOOP_MAX_COUNT,
  EXTENSION_LOOP_MAX_MS,
  SNIPE_LATE_TOLERANCE_SECONDS,
  fetchAuctionInfo,
} from "@yar/shared";
import type { ReservationJobData } from "../queues";
import { notifyUser } from "../notify";
import { launchBrowser, createYahooContext, markSessionExpired } from "../bidder/session";
import { placeBid, checkResult } from "../bidder/placeBid";
import { measureYahooTimeOffset, offsetIsStale, sleepUntil, sleep, yahooNow } from "../time";
import { tryAutoRaise } from "../autoRaise";
import { cancelGroupSiblings } from "../group";

// スナイプ実行本体(設計 §7)。入札予定時刻のウォームアップ分だけ手前
// (= T-(snipeSecondsBefore + MONITOR_WARMUP_SECONDS))で起動される。
// 1. ブラウザ+セッションのウォームアップ(失効ならこの時点で緊急通知)
// 2. T-(snipeSecondsBefore) まで待機して上限額で入札
// 3. 自動延長を検知したら上限額の範囲内で再スナイプループ
export async function runMonitorJob(job: Job<ReservationJobData>): Promise<void> {
  const reservation = await prisma.bidReservation.findUnique({
    where: { id: job.data.reservationId },
  });
  if (!reservation) return;
  if (reservation.status !== "SCHEDULED" && reservation.status !== "MONITORING") {
    return; // キャンセル済み・処理済み
  }

  await prisma.bidReservation.update({
    where: { id: reservation.id },
    data: { status: "MONITORING" },
  });

  if (offsetIsStale()) await measureYahooTimeOffset();

  let browser: Browser | undefined;
  let context: BrowserContext | undefined;
  try {
    browser = await launchBrowser();
    context = await createYahooContext(browser, reservation.yahooSessionId);
    const page = await context.newPage();

    // ウォームアップ: 商品ページを開いてログイン状態を確認
    await page.goto(reservation.auctionUrl, { waitUntil: "domcontentloaded" });

    await snipeLoop(page, reservation);
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    console.error(`[monitor] ${reservation.id} failed:`, detail);
    await failReservation(reservation, "PAGE_ERROR", detail);
  } finally {
    await context?.close().catch(() => {});
    await browser?.close().catch(() => {});
  }
}

async function snipeLoop(page: Page, reservation: BidReservation): Promise<void> {
  const loopStartedAt = Date.now();
  let endAt = reservation.endAt;
  let loopCount = 0;

  for (;;) {
    loopCount += 1;
    if (
      loopCount > EXTENSION_LOOP_MAX_COUNT ||
      Date.now() - loopStartedAt > EXTENSION_LOOP_MAX_MS
    ) {
      await failReservation(reservation, "TIMEOUT", "自動延長ループが上限に達しました");
      return;
    }

    // 直前の価格チェック(上限超過なら入札しない)
    const info = await fetchAuctionInfo(reservation.auctionUrl).catch(() => null);
    if (info?.endAt && info.endAt.getTime() !== endAt.getTime()) {
      endAt = info.endAt;
      await prisma.bidReservation.update({
        where: { id: reservation.id },
        data: { endAt },
      });
    }
    if (info?.currentPrice !== undefined && info.currentPrice >= reservation.maxBidAmount) {
      // ここは入札の直前。承認を待つ時間は無いので、自動増額(AUTO)だけ試す。
      // 承認制の予約に対してここで問い合わせても、返事が来る前に終了する。
      const outcome = await tryAutoRaise(
        { ...reservation, currentPrice: info.currentPrice },
        info.currentPrice,
        { allowApproval: false },
      );
      if (outcome.kind === "RAISED") {
        // 以降のループは増額後の額で入札する
        reservation.maxBidAmount = outcome.newAmount;
        reservation.autoRaiseUsedCount += 1;
      } else {
        await prisma.bidReservation.update({
          where: { id: reservation.id },
          data: { status: "EXPIRED", failureReason: "PRICE_OVER_LIMIT", currentPrice: info.currentPrice },
        });
        await notifyUser(reservation.userId, "EXPIRED", {
          title: reservation.title,
          url: reservation.auctionUrl,
          currentPrice: info.currentPrice,
          maxBidAmount: reservation.maxBidAmount,
          reason: outcome.kind === "DECLINED" ? outcome.message : undefined,
        });
        return;
      }
    }

    // スナイプ時刻まで待機
    const snipeAt = new Date(endAt.getTime() - reservation.snipeSecondsBefore * 1000);
    await sleepUntil(snipeAt);

    // sleepUntil は過去時刻なら即座に返る。つまり「起動が遅れた」ケースは
    // 待たずに通過してしまい、設定より遅い入札が無言で成立する。
    // スケジューラ側は snipeSecondsBefore からリードを算出しているので本来
    // ここは 0 に近いはずで、大きくズレたら worker 停止や Redis 詰まりを疑う。
    const lateBySec = Math.round((yahooNow().getTime() - snipeAt.getTime()) / 1000);
    const lateNote =
      lateBySec > SNIPE_LATE_TOLERANCE_SECONDS
        ? `予定より${lateBySec}秒遅れて実行(monitor の起動遅れ)`
        : null;
    if (lateNote) console.warn(`[monitor] ${reservation.id} ${lateNote}`);

    // 入札実行
    await prisma.bidReservation.update({
      where: { id: reservation.id },
      data: { status: "BIDDING" },
    });
    const scheduledFor = snipeAt;
    const result = await placeBid(page, reservation.auctionUrl, reservation.maxBidAmount);
    await prisma.bidAttempt.create({
      data: {
        reservationId: reservation.id,
        scheduledFor,
        executedAt: yahooNow(),
        bidAmount: reservation.maxBidAmount,
        outcome: result.outcome === "SUCCESS" ? "SUCCESS" : result.outcome,
        detail: [lateNote, "detail" in result ? result.detail : null]
          .filter(Boolean)
          .join(" / ") || null,
      },
    });

    if (result.outcome === "SESSION_EXPIRED") {
      await markSessionExpired(reservation.yahooSessionId);
      await failReservation(reservation, "SESSION_EXPIRED", "ヤフオクのログインが切れています");
      await notifyUser(reservation.userId, "SESSION_EXPIRED", {
        title: reservation.title,
        url: reservation.auctionUrl,
        hint: "手動での入札をご検討ください。設定画面から再連携できます。",
      });
      return;
    }
    if (result.outcome !== "SUCCESS") {
      // 1回だけ即時リトライ(設計 §7.3)
      const retry = await placeBid(page, reservation.auctionUrl, reservation.maxBidAmount);
      if (retry.outcome !== "SUCCESS") {
        await failReservation(reservation, retry.outcome, "detail" in retry ? retry.detail : undefined);
        return;
      }
    }

    // 終了を待って結果確認。自動延長ありの場合は延長を検知したらループ継続
    await sleepUntil(new Date(endAt.getTime() + 10_000));
    const after = await fetchAuctionInfo(reservation.auctionUrl).catch(() => null);

    if (
      reservation.hasAutoExtension &&
      after?.endAt &&
      after.endAt.getTime() > endAt.getTime() &&
      after.isClosed !== true
    ) {
      endAt = after.endAt;
      await prisma.bidReservation.update({
        where: { id: reservation.id },
        data: { endAt, status: "MONITORING" },
      });
      continue; // 再スナイプ
    }

    // 決着
    const verdict = await checkResult(page, reservation.auctionUrl);
    const won = verdict === "WON";
    await prisma.bidReservation.update({
      where: { id: reservation.id },
      data: {
        status: won ? "WON" : "LOST",
        resultPrice: after?.currentPrice ?? null,
        failureReason: verdict === "UNKNOWN" ? "RESULT_UNVERIFIED" : null,
      },
    });
    await notifyUser(reservation.userId, won ? "WON" : "LOST", {
      title: reservation.title,
      url: reservation.auctionUrl,
      finalPrice: after?.currentPrice ?? "不明",
      maxBidAmount: reservation.maxBidAmount,
    });

    // 落札したらグループの残りを取りやめる。ここで落ちても落札自体は
    // 成立しているので、通知を送ったあとに実行して例外を握りつぶさない。
    if (won) {
      try {
        const { cancelled, skipped } = await cancelGroupSiblings(reservation.id);
        if (cancelled || skipped) {
          console.log(`[group] ${reservation.id}: ${cancelled}件取りやめ / ${skipped}件は対象外`);
        }
      } catch (err) {
        console.error(`[group] ${reservation.id} の取りやめに失敗:`, err);
      }
    }
    return;
  }
}

async function failReservation(
  reservation: BidReservation,
  code: string,
  detail?: string,
): Promise<void> {
  await prisma.bidReservation.update({
    where: { id: reservation.id },
    data: {
      status: "FAILED",
      failureReason: detail ? `${code}: ${detail}` : code,
    },
  });
  await notifyUser(reservation.userId, "FAILED", {
    title: reservation.title,
    url: reservation.auctionUrl,
    reason: detail ?? code,
  });
}
