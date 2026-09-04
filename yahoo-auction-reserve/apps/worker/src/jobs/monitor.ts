import type { Job } from "bullmq";
import type { Browser, BrowserContext, Page } from "playwright";
import { prisma, type BidReservation } from "@yar/db";
import {
  EXTENSION_LOOP_MAX_COUNT,
  EXTENSION_LOOP_MAX_MS,
  SNIPE_LATE_TOLERANCE_SECONDS,
  fetchAuctionInfo,
  minimumBidToBeat,
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

/**
 * 予約を DB から読み直して、走行中に変わった内容を反映する。
 *
 * ⚠️ **これが「入札後に高値更新されたときの追加入札」の唯一の反映口**。
 * monitor はジョブ開始時に読んだ1行のまま最後まで走っていたので、Telegram の
 * 承認ボタンで増額しても Web で上限を上げても、走っている監視には届かなかった。
 * 2026-09-04 実測: 04:48 入札成功 → 自動延長 → 04:54 高値更新 → 上限超過で
 * 降りる、までの間に人が介入できる経路が1つも無かった。
 *
 * @returns 続行してよければ true。予約が消えた / 取りやめられたら false。
 */
async function syncReservation(reservation: BidReservation): Promise<boolean> {
  const fresh = await prisma.bidReservation.findUnique({ where: { id: reservation.id } });
  if (!fresh) {
    logMonitor(reservation, "予約が見つからないため監視を終了します");
    return false;
  }
  if (fresh.status === "CANCELLED") {
    // 同じグループの他を落札した等で取りやめられた。入札してはいけない。
    logMonitor(reservation, "予約が取りやめられたため監視を終了します");
    return false;
  }
  if (fresh.maxBidAmount !== reservation.maxBidAmount) {
    logMonitor(
      reservation,
      `上限額の変更を反映: ¥${reservation.maxBidAmount} → ¥${fresh.maxBidAmount}`,
    );
  }
  // ⚠️ endAt だけはこのループが持っている値のほうが新しいことがある
  // (延長を検知してから DB へ書くまでの間)。上書きすると延長前の終了時刻へ
  // 巻き戻り、スナイプ時刻が過去になって即入札 → 延長ループが空回りする。
  const endAt = reservation.endAt;
  Object.assign(reservation, fresh, { endAt });
  return true;
}

async function snipeLoop(page: Page, reservation: BidReservation): Promise<void> {
  const loopStartedAt = Date.now();
  let endAt = reservation.endAt;
  let loopCount = 0;
  // この監視ジョブで一度でも入札を出したか。
  // ⚠️ 入札していない回だけ EXPIRED で降りてよい。一度でも入札していたら
  // 落札できたかどうかは未確定なので、上限超過で入札を見送る回も終了まで
  // 見届けて WON / LOST を出す。ここで降りると最高額入札者だった予約が
  // 「スキップ」のまま終わり、結果通知が一度も届かない
  // (2026-09-04 実測: 04:48 入札成功 → 04:54 上限超過で EXPIRED → 決着通知なし)。
  let hasBid = false;
  // 同じ価格で「高値更新されました」を何度も送らないための直前値。
  let outbidNotifiedPrice = 0;

  for (;;) {
    loopCount += 1;
    if (
      loopCount > EXTENSION_LOOP_MAX_COUNT ||
      Date.now() - loopStartedAt > EXTENSION_LOOP_MAX_MS
    ) {
      await failReservation(reservation, "TIMEOUT", "自動延長ループが上限に達しました");
      return;
    }

    // 走行中に増額されていれば、ここで拾う
    if (!(await syncReservation(reservation))) return;

    // 直前の価格チェック(上限超過なら入札しない)
    const info = await fetchAuctionInfo(reservation.auctionUrl).catch(() => null);
    if (info?.endAt && info.endAt.getTime() !== endAt.getTime()) {
      endAt = info.endAt;
      // ⚠️ メモリ側も必ず合わせる。tryAutoRaise は reservation.endAt から
      // 承認の期限(編集締切)を出すので、ここが延長前のままだと期限が常に
      // 過去になり、**承認制の増額が自動延長ループで一度も成立しない**。
      // しかも DECLINED: NO_TIME に化けるので、ログを見ても「時間が無かった」
      // としか読めず、原因が終了時刻の同期漏れだと分からない。
      reservation.endAt = endAt;
      await prisma.bidReservation.update({
        where: { id: reservation.id },
        data: { endAt },
      });
    }
    // スナイプ時刻。増額の締切としても使うので、通知より先に確定させる。
    const snipeAt = new Date(endAt.getTime() - reservation.snipeSecondsBefore * 1000);

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
      // ⚠️ allowApproval は true 固定でよい。承認を待てるかどうかは
      // tryAutoRaise が reservation.endAt から出す編集締切が判定する。
      // 初回入札の回は monitor が起きた時点で既に締切を過ぎている
      // (締切 = 終了 - (snipe秒 + ウォームアップ + 余裕) < monitor の起動時刻)
      // ので必ず NO_TIME になり、「返事を待てない場面では聞かない」は自動的に
      // 守られる。逆に false 固定だと、5分近く猶予がある自動延長後でも聞けず、
      // 承認制を選んでいても高値更新にまったく対応できない。
      const outcome = await tryAutoRaise(
        { ...reservation, currentPrice: info.currentPrice },
        info.currentPrice,
        { allowApproval: true },
      );
      if (outcome.kind === "RAISED") {
        // 以降のループは増額後の額で入札する
        logMonitor(reservation, `自動増額: 上限を ¥${outcome.newAmount} に引き上げ`);
        reservation.maxBidAmount = outcome.newAmount;
        reservation.autoRaiseUsedCount += 1;
      } else if (!hasBid) {
        // まだ一度も入札していない = 落札の可能性が無い。終了まで待っても
        // LOST を出すだけなので、従来どおりスキップして降りる。
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
      } else if (info.currentPrice > outbidNotifiedPrice) {
        // 入札済みで抜かれた。オークションはまだ続いているので降りない。
        // スナイプ時刻までに上限を上げれば、下の読み直しで拾って入札しなおす。
        outbidNotifiedPrice = info.currentPrice;
        // ⚠️ 現在価格を DB へ書く。Web から増額するときの下限チェックが
        // この値を見るので、古いままだと「上限額は現在価格より高く」の
        // 判定が緩くなり、上回れない額での増額を通してしまう。
        await prisma.bidReservation.update({
          where: { id: reservation.id },
          data: { currentPrice: info.currentPrice },
        });
        logMonitor(
          reservation,
          `高値更新: 現在 ¥${info.currentPrice} / 上限 ¥${reservation.maxBidAmount}(増額を待ちます)`,
        );
        await notifyUser(reservation.userId, "OUTBID", {
          title: reservation.title,
          url: reservation.auctionUrl,
          currentPrice: info.currentPrice,
          maxBidAmount: reservation.maxBidAmount,
          requiredAmount: minimumBidToBeat(info.currentPrice),
          _lines: [
            `再入札の予定: ${snipeAt.toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" })}`,
            "それまでに上限額を上げれば、この予約のまま入札しなおします。",
          ],
        });
      }
    }

    // スナイプ時刻まで待機
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

    // ⚠️ 入札の直前にもう一度読み直す。上の「高値更新」通知を見て上限を
    // 上げた場合、反映されるのはここだけ。待つ前の値のまま入札すると、
    // 増額したのに古い額で入札して必ず負ける(しかも成功と報告される)。
    if (!(await syncReservation(reservation))) return;
    const required =
      info?.currentPrice !== undefined ? minimumBidToBeat(info.currentPrice) : null;
    const scheduledFor = snipeAt;

    if (required !== null && reservation.maxBidAmount < required) {
      // 上限が足りないので入札はしない。⚠️ ここで return しないこと。
      // 一度入札している以上、落札できたかどうかを終了まで見届けて
      // WON / LOST を出す必要がある。降りると結果が永久に出ない。
      logMonitor(
        reservation,
        `入札を見送り: 上限 ¥${reservation.maxBidAmount} では現在価格 ¥${info?.currentPrice} を上回れません` +
          `(必要額 ¥${required})`,
      );
      await prisma.bidAttempt.create({
        data: {
          reservationId: reservation.id,
          scheduledFor,
          executedAt: yahooNow(),
          bidAmount: reservation.maxBidAmount,
          outcome: "OUTBID",
          detail: `高値更新のため入札を見送り(現在価格 ¥${info?.currentPrice} / 必要額 ¥${required})`,
        },
      });
    } else {
      // 入札実行
      await prisma.bidReservation.update({
        where: { id: reservation.id },
        data: { status: "BIDDING" },
      });

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
          // 描画待ちの上限を切るために残り時間を渡す(settleBudgetMs)。
          // これが無いと、5秒前入札の予約で描画を待っている間に終わる。
          remainingMs: endAt.getTime() - yahooNow().getTime(),
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
      } else if (result.outcome === "ALREADY_HIGHEST") {
        // ⚠️ この分岐も `!== "SUCCESS"` より **前**(else if で繋いでいる)。
        // すでに自分が最高額入札者だったので押さなかった、という結末は失敗ではない。
        // 後ろに置くとリトライに落ちるが、読み直しても同じ状態なので2回目も
        // ALREADY_HIGHEST になり、最終的に FAILED = 最高額を保っているのに
        // 「入札に失敗しました」が飛ぶ。
        // ⚠️ ここは return しない。落札できたかどうかは未確定なので、
        // 下の終了待ち → checkResult に流して WON / LOST を出す必要がある。
        await notifyUser(reservation.userId, "ALREADY_HIGHEST", {
          title: reservation.title,
          url: reservation.auctionUrl,
          maxBidAmount: reservation.maxBidAmount,
          detail: result.detail,
        });
        logMonitor(reservation, `入札せず(すでに最高額入札者): ${result.detail}`);
      } else if (result.outcome !== "SUCCESS") {
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
            // 1回目で時間を使っているので、ここで測り直す
            remainingMs: endAt.getTime() - yahooNow().getTime(),
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
      // ここまで来たら「最高額入札者になれた可能性がある」。以後は上限超過で
      // 入札を見送っても、終了まで見届けて結果を出す。
      hasBid = true;
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
      // ⚠️ syncReservation が DB の値で上書きしないよう、メモリ側も進める
      reservation.endAt = endAt;
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
