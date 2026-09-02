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
import { settlePage } from "../bidder/settle";
import { measureYahooTimeOffset, offsetIsStale, sleepUntil, sleep, yahooNow } from "../time";
import { tryAutoRaise } from "../autoRaise";
import { cancelGroupSiblings } from "../group";
import { acquireSessionLock, sessionLockWaitMs } from "../sessionLock";

// monitor は「何もしなかった」ときと「判断して見送った」ときが
// ログ上で見分けられない状態だった。2026-08-30 に上限超過で入札を
// 見送った回は DB の failureReason にしか痕跡が無く、ログを見ても
// 起動したことすら分からなかった。判断の分岐点では必ず1行出す。
// (時刻は docker/journald 側が付けるのでここでは出さない = JST/UTC 事故を避ける)
function logMonitor(reservation: { id: string; auctionId: string }, message: string): void {
  console.log(`[monitor] ${reservation.auctionId} (${reservation.id}) ${message}`);
}

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
  logMonitor(
    reservation,
    `監視開始: 上限 ¥${reservation.maxBidAmount} / ` +
      `${reservation.snipeSecondsBefore}秒前に入札${reservation.dryRun ? " (テスト実行)" : ""}`,
  );

  if (offsetIsStale()) await measureYahooTimeOffset();

  let browser: Browser | undefined;
  let context: BrowserContext | undefined;
  try {
    browser = await launchBrowser();
    context = await createYahooContext(browser, reservation.yahooSessionId);
    const page = await context.newPage();

    // ウォームアップ: 商品ページを開いてログイン状態を確認
    await page.goto(reservation.auctionUrl, { waitUntil: "domcontentloaded" });
    // ⚠️ 新UIは CSR。`domcontentloaded` 直後の DOM はほぼ空(セレクタ表の地雷5)。
    // 描画を待つ処理がプローブにしか無く、ジョブ側が待っていない状態は
    // ウォッチリスト同期で一度やらかしている(settle.ts の警告)。入札までは
    // MONITOR_WARMUP_SECONDS ぶん余裕があるので、ここで待って結果を残す。
    // 残す理由: 入札に失敗した後で「そもそも描画されていたのか」を
    // 問えるようにするため。ここが NG のまま失敗したなら原因は描画側。
    const settled = await settlePage(page).catch(() => null);
    logMonitor(
      reservation,
      settled
        ? `ウォームアップ: クリック要素${settled.clickable}個 / 入力欄${settled.inputs}個 / ` +
            `描画判定 ${settled.verdict.rendered ? "OK" : `NG(${settled.verdict.reason})`}`
        : "ウォームアップ: 描画待ちに失敗(計測できず)",
    );

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
    if (info?.currentPrice === undefined) {
      // 取れないまま入札には進む(上限額での入札自体はヤフオク側が弾く)。
      // 「確認できなかった」ことをここで残さないと、上限判定を一度も
      // 通していないのに通したように見える。
      logMonitor(reservation, "価格確認: 取得できず(上限チェックを行えていない)");
    } else {
      logMonitor(
        reservation,
        `価格確認: 現在 ¥${info.currentPrice} / 上限 ¥${reservation.maxBidAmount}`,
      );
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
        logMonitor(reservation, `自動増額: 上限を ¥${outcome.newAmount} に引き上げ`);
        reservation.maxBidAmount = outcome.newAmount;
        reservation.autoRaiseUsedCount += 1;
      } else {
        logMonitor(
          reservation,
          `入札しません: 現在価格 ¥${info.currentPrice} が上限 ¥${reservation.maxBidAmount} 以上` +
            `(自動増額: ${outcome.kind})`,
        );
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

    // 同一アカウントからの入札は重ねない(設計 §7.4)。ただし待つのは
    // 「待っても入札に間に合う」範囲だけで、取れなければそのまま実行する。
    // ここで無制限に待つと、同じアカウントで終了時刻が近い2件を予約した
    // 瞬間に片方が入札されずに終わる。
    const lease = await acquireSessionLock(
      reservation.yahooSessionId,
      sessionLockWaitMs(yahooNow().getTime(), endAt.getTime()),
    );
    if (!lease.serialized) {
      console.warn(
        `[monitor] ${reservation.id} 同一セッションの入札と並行実行します` +
          `(${lease.waitedMs}ms 待機。終了が近いため直列化を諦めました)`,
      );
    }

    let result;
    try {
      result = await placeBid(page, reservation.auctionUrl, reservation.maxBidAmount, undefined, {
        dryRun: reservation.dryRun,
      });
    } finally {
      // 入札の送信だけがロックの対象。この後の結果確認・終了待ちまで
      // 抱えると、同じアカウントの次の予約が最大30分待たされる。
      lease.release();
    }
    logMonitor(
      reservation,
      `入札実行: ¥${reservation.maxBidAmount} → ${result.outcome}` +
        ("detail" in result && result.detail ? ` (${result.detail})` : ""),
    );
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
    // ⚠️ この分岐は下の `!== "SUCCESS"` より **前** に置くこと。
    // 後ろに置くと DRY_RUN が「入札に失敗した」と読まれてリトライされ、
    // 2回目も DRY_RUN なので最終的に FAILED になる。テスト実行が成功したのに
    // 失敗通知が飛ぶ = 何を確かめたのか分からなくなる。
    if (result.outcome === "DRY_RUN") {
      await prisma.bidReservation.update({
        where: { id: reservation.id },
        data: { status: "DRY_RUN", failureReason: null },
      });
      // 通知は必ず出す。テスト実行の目的は「予定時刻に本当に動いたか」の確認で、
      // 静かに終わると動いていない場合と区別が付かない。
      await notifyUser(reservation.userId, "DRY_RUN", {
        title: reservation.title,
        url: reservation.auctionUrl,
        maxBidAmount: reservation.maxBidAmount,
        detail: result.detail,
        lateBySec: `${lateBySec}秒`,
      });
      console.log(`[monitor] ${reservation.id} テスト実行完了: ${result.detail}`);
      return;
    }

    if (result.outcome !== "SUCCESS") {
      // 1回だけ即時リトライ(設計 §7.3)。ここも同一アカウントの送信なので
      // ロックを取り直す(1回目で解放しているので、間に他の予約が入りうる)。
      const retryLease = await acquireSessionLock(
        reservation.yahooSessionId,
        sessionLockWaitMs(yahooNow().getTime(), endAt.getTime()),
      );
      let retry;
      try {
        // ⚠️ リトライは **必ず読み直す**。同じ page を再利用すると、
        // 1回目に開いたモーダルや空の DOM をそのまま触ることになり、
        // 2回目が1回目と同じ理由で落ちることが確定する
        // (2026-09-02: 同じ Timeout を15秒×2回出して終わった)。
        retry = await placeBid(page, reservation.auctionUrl, reservation.maxBidAmount, undefined, {
          dryRun: reservation.dryRun,
          reload: true,
        });
      } finally {
        retryLease.release();
      }
      // ⚠️ リトライの結果も必ず残す。ここが無いと、失敗した予約の
      // BidAttempt が1件しか無く、2回目に何が起きたのかが永久に分からない
      // (1回目と同じ理由で落ちたのか、別の理由なのかが切り分けられない)。
      await prisma.bidAttempt.create({
        data: {
          reservationId: reservation.id,
          scheduledFor,
          executedAt: yahooNow(),
          bidAmount: reservation.maxBidAmount,
          outcome: retry.outcome,
          detail: `リトライ / ${"detail" in retry ? retry.detail : "(詳細なし)"}`,
        },
      });
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
    const { verdict, reason } = await checkResult(page, reservation.auctionUrl);
    logMonitor(reservation, `結果判定: ${verdict} - ${reason}`);
    const won = verdict === "WON";
    // ⚠️ UNKNOWN を LOST に畳まないこと。落札しているのに「落札ならず」を
    // 送ると、取引ナビが立っているのに誰も気づかず、出品者と落札者の双方が
    // こちらの沈黙を待つ。分からないときは FAILED(=人間が確認する状態)にする。
    // 2026-08-29 まで checkResult は構造上 UNKNOWN しか返せなかったので、
    // この経路は「必ず LOST を通知する」状態だった。
    const status = verdict === "UNKNOWN" ? "FAILED" : verdict;
    await prisma.bidReservation.update({
      where: { id: reservation.id },
      data: {
        status,
        resultPrice: after?.currentPrice ?? null,
        failureReason: verdict === "UNKNOWN" ? `RESULT_UNVERIFIED: ${reason}` : null,
      },
    });
    if (verdict === "UNKNOWN") {
      await notifyUser(reservation.userId, "FAILED", {
        title: reservation.title,
        url: reservation.auctionUrl,
        reason: `落札できたかどうかを確認できませんでした(${reason})`,
        hint: "ヤフオクの「マイオク > 落札」で結果を確認してください",
        finalPrice: after?.currentPrice ?? "不明",
        maxBidAmount: reservation.maxBidAmount,
      });
    } else {
      await notifyUser(reservation.userId, won ? "WON" : "LOST", {
        title: reservation.title,
        url: reservation.auctionUrl,
        finalPrice: after?.currentPrice ?? "不明",
        maxBidAmount: reservation.maxBidAmount,
      });
    }

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
  // ⚠️ ここに console が無かったせいで、2026-08-28 のテスト実行は
  // worker のログに1行も残らなかった(記録は DB の1行だけ)。
  // 入札はこのシステムが存在する唯一の瞬間なので、失敗は必ずログに出す。
  console.error(`[monitor] ${reservation.id} 失敗(${code}): ${detail ?? "(詳細なし)"}`);
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
