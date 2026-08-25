import type { Browser } from "playwright";
import { prisma } from "@yar/db";
import { selectors } from "../bidder/selectors";
import { createYahooContext, launchBrowser, markSessionExpired } from "../bidder/session";
import { notifyUser } from "../notify";
import { judgeSession, planVerifyOutcome } from "../sessionVerdict";

// 連携 Cookie の生存確認(設計 §8-3)。
//
// 登録時にできるのは形式チェックだけで、ログインが切れていても登録は通る。
// 何もしないと、切れていることが分かるのは **入札の瞬間** になる。
// ここで定期的に開いて、切れていれば先に通知して再連携してもらう。
//
// ⚠️ 判定の非対称性: EXPIRED にすると、そのセッションの予約が全部止まる。
// 判定できなかった(UNKNOWN)ときは何もしない。詳細は sessionVerdict.ts。

/** 1セッションあたりの確認間隔。ブラウザを起動するので粗く回す */
const VERIFY_INTERVAL_MS = 6 * 60 * 60 * 1000;
/** 1回の走査で確認する上限。全件を一度に開くとブラウザ起動が詰まる */
const VERIFY_BATCH = 3;
/** 予約もウォッチもない連携の確認先。ログインリンクの有無で判定する */
const FALLBACK_URL = "https://auctions.yahoo.co.jp/";

export interface VerifySessionResult {
  kind: "ACTIVE" | "EXPIRED" | "UNKNOWN";
  reason: string;
  /** 実際に開いた URL(判定の根拠を残す) */
  url: string;
}

/**
 * 確認先の URL を選ぶ。
 *
 * 予約中の商品ページを最優先にする。P0 実測(2026-08-24)でログイン有無の
 * 差を確認できているのは商品ページの `loginLink` だけなので、そこで見るのが
 * 一番確実。無ければウォッチリストの商品、それも無ければトップページ。
 */
async function pickTargetUrl(yahooSessionId: string, userId: string): Promise<string> {
  const reservation = await prisma.bidReservation.findFirst({
    where: { yahooSessionId, status: { in: ["SCHEDULED", "MONITORING"] } },
    orderBy: { endAt: "asc" },
    select: { auctionUrl: true },
  });
  if (reservation) return reservation.auctionUrl;

  const watched = await prisma.watchlistItem.findFirst({
    where: { userId, dismissedAt: null },
    orderBy: { lastSeenAt: "desc" },
    select: { auctionUrl: true },
  });
  return watched?.auctionUrl ?? FALLBACK_URL;
}

export async function verifySession(yahooSessionId: string): Promise<VerifySessionResult> {
  const session = await prisma.yahooSession.findUnique({ where: { id: yahooSessionId } });
  if (!session || session.status !== "ACTIVE") {
    return { kind: "UNKNOWN", reason: "連携が有効ではありません", url: "" };
  }

  // 試行時刻は結果より先に立てる。ここで失敗して例外が飛んでも
  // 「試した」事実は残り、次の走査では他の連携に順番が回る。
  await prisma.yahooSession.update({
    where: { id: yahooSessionId },
    data: { lastVerifyAttemptAt: new Date() },
  });

  const url = await pickTargetUrl(yahooSessionId, session.userId);

  let browser: Browser | undefined;
  let result: VerifySessionResult;
  try {
    browser = await launchBrowser();
    const context = await createYahooContext(browser, yahooSessionId);
    const page = await context.newPage();
    await page.goto(url, { waitUntil: "domcontentloaded" });

    const verdict = judgeSession({
      finalUrl: page.url(),
      loginLinkCount: await page.locator(selectors.loginLink).count(),
      loggedInIndicatorCount: await page.locator(selectors.loggedInIndicator).count(),
    });
    result = { kind: verdict.verdict, reason: verdict.reason, url };
  } finally {
    await browser?.close().catch(() => {});
  }

  const plan = planVerifyOutcome({ verdict: result.kind, reason: result.reason });
  if (plan.markExpired) {
    await markSessionExpired(yahooSessionId);
    await notifyUser(session.userId, "SESSION_EXPIRED", {
      title: `連携「${session.label}」`,
      hint: `${result.reason}。設定画面から再連携してください`,
      url,
    });
  } else if (plan.advanceVerifiedAt) {
    await prisma.yahooSession.update({
      where: { id: yahooSessionId },
      data: { lastVerifiedAt: new Date() },
    });
  }
  if (plan.warn) {
    // 判定できない状態が続くと、この確認は「静かに何もしていない」のと
    // 同じになる。lastVerifiedAt が進まないので日次サマリに古い時刻が出る。
    console.warn(
      `[verifySession] ${session.label}: ${result.reason} (${url})。` +
        "セレクタ(loginLink / loggedInIndicator)の確認が必要かもしれません",
    );
  }
  return result;
}

/**
 * 登録直後の未確認セッションだけを見る速い走査(P1)。
 *
 * 登録できたのにログインが切れている、という状態は **登録直後にこそ**
 * 直したい。6時間おきの定期走査に任せると、次の走査までそれが分からない。
 * かといって定期走査そのものを速く回すと、走査のたびに全連携でブラウザが
 * 立ち上がる。「まだ一度も試していない」ものだけを別レーンで拾う。
 *
 * ⚠️ 空振りし続けることはない。verifySession() は試行時刻を **開く前に**
 * 立てるので、失敗しても lastVerifyAttemptAt は埋まり、この条件から外れる。
 * (条件を lastVerifiedAt(成功時刻)にすると、判定不能な連携を30秒ごとに
 *  永久に開き続ける。)
 */
export async function runNewSessionVerifySweep(): Promise<void> {
  const sessions = await prisma.yahooSession.findMany({
    where: { status: "ACTIVE", lastVerifyAttemptAt: null },
    orderBy: { createdAt: "asc" },
    take: VERIFY_BATCH,
    select: { id: true, label: true },
  });
  await runVerifyBatch(sessions);
}

/** 確認期限の来た ACTIVE な連携を順に見る。スケジューラから定期的に呼ぶ */
export async function runVerifySessionSweep(): Promise<void> {
  const due = new Date(Date.now() - VERIFY_INTERVAL_MS);
  const sessions = await prisma.yahooSession.findMany({
    where: {
      status: "ACTIVE",
      OR: [{ lastVerifyAttemptAt: null }, { lastVerifyAttemptAt: { lt: due } }],
    },
    // 未確認(null)を先に、次に確認が古い順。失敗し続ける1件が先頭に
    // 居座らないよう、成功時刻ではなく試行時刻で並べる。
    orderBy: { lastVerifyAttemptAt: { sort: "asc", nulls: "first" } },
    take: VERIFY_BATCH,
    select: { id: true, label: true },
  });

  await runVerifyBatch(sessions);
}

async function runVerifyBatch(sessions: { id: string; label: string }[]): Promise<void> {
  for (const s of sessions) {
    try {
      const r = await verifySession(s.id);
      console.log(`[verifySession] ${s.label}: ${r.kind} - ${r.reason}`);
    } catch (err) {
      // 1件の失敗で他の連携の確認を止めない。失効にもしない
      // (ネットワーク断とログイン切れは区別できない)。
      console.error(`[verifySession] ${s.label} の確認に失敗:`, err);
    }
  }
}
