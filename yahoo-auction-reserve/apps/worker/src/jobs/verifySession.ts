import type { Browser } from "playwright";
import { prisma } from "@yar/db";
import { selectors } from "../bidder/selectors";
import { createYahooContext, launchBrowser, markSessionExpired } from "../bidder/session";
import { notifyUser } from "../notify";
import { judgeSession, planVerifyOutcome } from "../sessionVerdict";
import { WATCHLIST_URL_CANDIDATES } from "./watchlist";

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
/**
 * 生存確認を行うページ。**ウォッチリスト固定**。
 *
 * ⚠️ 2026-08-30 まではここが予約中の商品ページだった。結果、4回中4回が
 * UNKNOWN になり、この確認は「静かに何もしていない」状態だった。
 * 商品ページは新UI(CSR)で `loginLink` も `loggedInIndicator` も 0件になり、
 * **ログイン中と失効が同じ見た目**になる。判定に必要なのは片方の実測ではなく
 * 陰陽の対照で、それが揃っているのはウォッチリストだけ:
 *
 * - ログイン中 (2026-08-26 実測): `loggedInIndicator` 1件 / `loginLink` 0件 → ACTIVE
 * - 未ログイン (2026-08-29 実測): `login.yahoo.co.jp/config/login?...` へ 302
 *   (HTTP は 200 のまま) → 到達 URL で EXPIRED
 *
 * ウォッチが0件でもページ自体は開けるので、件数には依存しない。
 * URL は同期ジョブと同じものを参照する(片方だけ直して気づかない事故を防ぐ)。
 */
const VERIFY_TARGET_URL = WATCHLIST_URL_CANDIDATES[0]!;

export interface VerifySessionResult {
  kind: "ACTIVE" | "EXPIRED" | "UNKNOWN";
  reason: string;
  /** 実際に開いた URL(判定の根拠を残す) */
  url: string;
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

  const url = VERIFY_TARGET_URL;

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
    // ⚠️ ウォッチリストで判断できないなら、それは「たまたま」ではなく
    // ページ構造が変わった疑いが濃い(ここは陰陽の対照が取れている唯一の面)。
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
