import { NextResponse } from "next/server";
import { prisma } from "@yar/db";
import { judgeManualWatchlistSync } from "@yar/shared";
import { requireUser } from "@/lib/auth";
import { handle, jsonError } from "@/lib/api";

// 「今すぐ更新」の受け口。
//
// ⚠️ ここで同期そのものを走らせない。Playwright/Chromium は worker イメージ
// にしか入っておらず、web からヤフオクは開けない。web は要求を立てるだけに
// して、worker の30秒走査に拾わせる(jobs/watchlist.ts の
// runWatchlistRequestSweep)。ヤフオクに触るのは worker だけという分担を保つ。
//
// ⚠️ 返すのは時刻と状態だけ。Cookie・連携の中身は一切返さない(設計 §8)。

export const dynamic = "force-dynamic";

function activeSessions(userId: string) {
  return prisma.yahooSession.findMany({
    where: { userId, status: "ACTIVE" },
    select: { lastWatchlistSyncAt: true, watchlistSyncRequestedAt: true },
  });
}

/** 同期を1回要求する */
export async function POST() {
  return handle(async () => {
    const user = await requireUser();
    const sessions = await activeSessions(user.id);
    const verdict = judgeManualWatchlistSync(sessions, Date.now());

    if (verdict.kind === "NO_SESSION") {
      return jsonError(409, "ヤフオク連携がありません。設定画面から連携してください");
    }
    if (verdict.kind === "TOO_SOON") {
      return NextResponse.json(
        {
          error: `同期したばかりです。あと${verdict.retryAfterSec}秒お待ちください`,
          retryAfterSec: verdict.retryAfterSec,
        },
        { status: 429, headers: { "Retry-After": String(verdict.retryAfterSec) } },
      );
    }
    if (verdict.kind === "ACCEPT") {
      await prisma.yahooSession.updateMany({
        where: { userId: user.id, status: "ACTIVE" },
        data: { watchlistSyncRequestedAt: new Date() },
      });
    }
    // PENDING はすでに要求済み。立て直さずそのまま待たせる
    // (立て直すと、押すたびに要求時刻が前に進んで歯止めが効かなくなる)
    return NextResponse.json({ pending: true }, { status: 202 });
  });
}

/** 待っている画面が同期の終わりを見張るための状態 */
export async function GET() {
  return handle(async () => {
    const user = await requireUser();
    const sessions = await activeSessions(user.id);
    const syncedMs = sessions
      .map((s) => s.lastWatchlistSyncAt?.getTime())
      .filter((ms): ms is number => ms != null);
    return NextResponse.json({
      lastSyncAtMs: syncedMs.length > 0 ? Math.max(...syncedMs) : null,
      pending: sessions.some((s) => s.watchlistSyncRequestedAt != null),
    });
  });
}
