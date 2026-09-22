import { prisma } from "@yar/db";
import {
  SNIPE_SECONDS_MAX,
  formatJstDayLabel,
  formatJstTime,
  formatRemaining,
  monitorLeadSeconds,
  planPreflight,
  preflightScanHorizonMs,
} from "@yar/shared";
import { SESSION_STATUS_LABEL, type SessionStatusKey } from "@yar/shared/labels";
import { notifyUser } from "../notify";
import { verifySession } from "./verifySession";

// 入札の手前で、その予約が使う連携が生きているかを先に確かめる(案 C)。
//
// なぜ既存の生存確認では足りないか:
//   runVerifySessionSweep() は `status: "ACTIVE"` の連携しか走査しない。
//   一方 BidReservation.yahooSessionId は **予約を作った時点で固定** される。
//   再連携しても新しい連携は別レコードなので、古い予約は失効した連携を
//   指し続け、**どの走査にも載らないまま** 入札の瞬間に失敗する。
//   (2026-09-22 実測。このときは実行前の予約が0件だったので実害は出なかった)
//
// だからここは「有効な連携」ではなく **予約の側** から引く。
// 判定そのものは packages/shared/src/preflight.ts(テスト済み)に置いてある。

/** 1回の走査でブラウザを開く上限。通知だけで済む分はここに数えない */
const PREFLIGHT_BROWSER_BATCH = 2;

/** 事前確認の対象になる予約の状態 */
const TARGET_STATUSES = ["SCHEDULED", "MONITORING"] as const;

export interface PreflightCandidate {
  id: string;
  endAt: Date;
  snipeSecondsBefore: number;
  sessionStatus: SessionStatusKey;
  sessionLastVerifiedAt: Date | null;
}

export interface PreflightAction {
  id: string;
  kind: "notify-dead" | "trust" | "too-late" | "verify";
}

/**
 * どの予約に何をするかを決める。DB もブラウザも触らないのでそのままテストできる。
 *
 * ⚠️ 選ばれなかった予約には **印を付けない**。印は「一度見た」の記録なので、
 *    見ていないのに付けると、その予約は二度と対象にならないまま入札を迎える。
 *    枠から溢れた分は次の走査(5分後)に回る。窓は最短でも55分あるので必ず届く。
 *
 * @param rows          走査で引いた候補(終了が近い順)
 * @param now           現在時刻
 * @param browserBudget この走査でブラウザを開いてよい上限
 */
export function selectPreflightActions(
  rows: PreflightCandidate[],
  now: Date,
  browserBudget: number,
): PreflightAction[] {
  const out: PreflightAction[] = [];
  let opens = 0;

  for (const r of rows) {
    const plan = planPreflight({
      now,
      endAt: r.endAt,
      snipeSecondsBefore: r.snipeSecondsBefore,
      sessionStatus: r.sessionStatus,
      sessionLastVerifiedAt: r.sessionLastVerifiedAt,
    });

    if (plan.kind === "wait") continue;

    if (plan.kind === "verify") {
      // ⚠️ 枠を使うのは verify だけ。通知・trust・too-late をここに数えると、
      //    死んだ連携が並んだ日に後ろの予約が黙って落ちる
      if (opens >= browserBudget) continue;
      opens += 1;
    }

    out.push({ id: r.id, kind: plan.kind });
  }

  return out;
}

/** 「9/22(月) 22:00」。窓が日付をまたぐことがあるので日付も出す */
function endAtLabel(d: Date): string {
  return `${formatJstDayLabel(d)} ${formatJstTime(d, false)}`;
}

/** 入札(monitor の起動)まで、あとどれだけ残っているか */
function remainingLabel(now: Date, endAt: Date, snipeSecondsBefore: number): string {
  const monitorStartMs = endAt.getTime() - monitorLeadSeconds(snipeSecondsBefore) * 1000;
  return formatRemaining(monitorStartMs - now.getTime());
}

function hintFor(status: SessionStatusKey): string {
  // ⚠️ 「再連携してください」だけでは直らない。予約は登録時の連携に
  //    固定されるので、再連携して作られた **新しい連携を使う予約** に
  //    し直す必要がある。ここを書き落とすと、再連携した人が
  //    「直したのにまた失敗した」に突き当たる。
  const base =
    status === "REVOKED"
      ? "この予約が使う連携は解除済みです"
      : "この予約が使う連携でヤフオクにログインできません";
  return `${base}。設定画面で連携し直したうえで、この予約を登録し直してください(予約は登録時の連携に固定されます)`;
}

export async function runPreflightSweep(): Promise<void> {
  const now = new Date();
  // 実行秒数が最大の予約でも取りこぼさないよう広めに引き、
  // 正確な判定は selectPreflightActions() に任せる。
  const horizon = new Date(now.getTime() + preflightScanHorizonMs(SNIPE_SECONDS_MAX));

  const rows = await prisma.bidReservation.findMany({
    where: {
      status: { in: [...TARGET_STATUSES] },
      preflightAt: null,
      endAt: { lte: horizon },
    },
    orderBy: { endAt: "asc" },
    select: {
      id: true,
      userId: true,
      title: true,
      auctionId: true,
      auctionUrl: true,
      endAt: true,
      snipeSecondsBefore: true,
      yahooSessionId: true,
      yahooSession: { select: { label: true, status: true, lastVerifiedAt: true } },
    },
  });

  const byId = new Map(rows.map((r) => [r.id, r]));
  const actions = selectPreflightActions(
    rows.map((r) => ({
      id: r.id,
      endAt: r.endAt,
      snipeSecondsBefore: r.snipeSecondsBefore,
      sessionStatus: r.yahooSession.status as SessionStatusKey,
      sessionLastVerifiedAt: r.yahooSession.lastVerifiedAt,
    })),
    now,
    PREFLIGHT_BROWSER_BATCH,
  );

  for (const action of actions) {
    const r = byId.get(action.id);
    if (!r) continue;

    // ⚠️ 印を先に立て、立てられた側だけが動く。worker が2つ動いても
    //    同じ予約で二重に通知・二重にブラウザ起動しない。
    const claim = await prisma.bidReservation.updateMany({
      where: { id: r.id, preflightAt: null },
      data: { preflightAt: now },
    });
    if (claim.count !== 1) continue;

    const label = r.title || r.auctionId;
    const sessionStatus = r.yahooSession.status as SessionStatusKey;

    if (action.kind === "notify-dead") {
      await notifyUser(r.userId, "SESSION_DEAD_BEFORE_BID", {
        title: label,
        url: r.auctionUrl,
        endAt: endAtLabel(r.endAt),
        remaining: remainingLabel(now, r.endAt, r.snipeSecondsBefore),
        sessionStatus: `${r.yahooSession.label} (${SESSION_STATUS_LABEL[sessionStatus]})`,
        hint: hintFor(sessionStatus),
      });
      console.log(`[preflight] ${label}: 連携 ${sessionStatus} のため通知しました`);
      continue;
    }

    if (action.kind === "trust" || action.kind === "too-late") {
      console.log(`[preflight] ${label}: ${action.kind}(ブラウザは開きません)`);
      continue;
    }

    try {
      const result = await verifySession(r.yahooSessionId);
      console.log(`[preflight] ${label}: 連携の確認 ${result.kind} - ${result.reason}`);
      if (result.kind === "EXPIRED") {
        // ⚠️ verifySession 自身も SESSION_EXPIRED を出すが、あれは
        //    「連携が切れた」であって「どの予約が失敗するか」を言わない。
        //    入札の手前で要るのは後者なので、二重になっても両方出す。
        await notifyUser(r.userId, "SESSION_DEAD_BEFORE_BID", {
          title: label,
          url: r.auctionUrl,
          endAt: endAtLabel(r.endAt),
          remaining: remainingLabel(now, r.endAt, r.snipeSecondsBefore),
          reason: result.reason,
          hint: hintFor("EXPIRED"),
        });
      }
    } catch (err) {
      // ⚠️ 黙って飲まない。ここで飲むと「事前確認そのものが動かなくなった」
      //    ことが誰にも見えない(この機能を足した目的がそれ)。
      //    印は付けたままにする。同じ予約で走査ごとにブラウザを起動し直すと、
      //    入札直前の Mac の資源を食い潰すほうが害が大きい。
      console.error(`[preflight] ${label} の事前確認に失敗:`, err);
      await notifyUser(r.userId, "SESSION_DEAD_BEFORE_BID", {
        title: label,
        url: r.auctionUrl,
        endAt: endAtLabel(r.endAt),
        remaining: remainingLabel(now, r.endAt, r.snipeSecondsBefore),
        reason: "入札前の連携確認を実行できませんでした(連携が切れているとは限りません)",
        hint: "設定画面で連携の状態を確認してください",
      }).catch((e) => console.error("[preflight] 通知にも失敗:", e));
    }
  }
}
