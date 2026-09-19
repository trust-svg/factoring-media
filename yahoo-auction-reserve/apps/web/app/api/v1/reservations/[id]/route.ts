import { NextResponse, type NextRequest } from "next/server";
import { prisma } from "@yar/db";
import {
  cancelVerdict,
  editDeadlineSeconds,
  SNIPE_SECONDS_MAX,
  SNIPE_SECONDS_MIN,
  validateAutoRaiseInput,
  validateRunningRaise,
  type AutoRaiseFields,
} from "@yar/shared";
import { requireUser } from "@/lib/auth";
import { handle, jsonError } from "@/lib/api";

async function findOwned(id: string, userId: string) {
  const reservation = await prisma.bidReservation.findUnique({
    where: { id },
    include: { attempts: { orderBy: { createdAt: "asc" } } },
  });
  return reservation && reservation.userId === userId ? reservation : null;
}

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  return handle(async () => {
    const user = await requireUser();
    const reservation = await findOwned((await params).id, user.id);
    if (!reservation) return jsonError(404, "予約が見つかりません");
    return NextResponse.json(reservation);
  });
}

// 上限額・実行秒数の変更は SCHEDULED かつ締切前のみ(設計 §9)
export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  return handle(async () => {
    const user = await requireUser();
    const reservation = await findOwned((await params).id, user.id);
    if (!reservation) return jsonError(404, "予約が見つかりません");
    // 走行中(監視中・入札中)は「上限額の引き上げ」だけ受ける。
    //
    // ⚠️ 締切(editDeadlineSeconds)の判定はここでは行わない。あの締切は
    // 「monitor が起動時に読んだ内容のまま走るので、起動後に書いても
    // 反映されない」ことから来ていた。monitor はスナイプ時刻の直前に
    // 予約を読み直すようになったので(jobs/monitor.ts の syncReservation)、
    // 終了直前でも書けば拾われる。ここを塞ぐと、入札後に高値更新された
    // ときに増額する手段が無くなり、**この機能そのものが成立しない**。
    //
    // 引き下げとその他の項目を受けないのは、送信済みの入札を取り消せない
    // から。上限を下げても効果が無く、実行秒数やテスト実行を今さら変えると
    // 走っているループが持っている前提と食い違う。
    if (reservation.status === "MONITORING" || reservation.status === "BIDDING") {
      const raise = validateRunningRaise(await req.json(), reservation, Date.now());
      if (!raise.ok) return jsonError(raise.status, raise.error);
      const updated = await prisma.bidReservation.update({
        where: { id: reservation.id },
        data: { maxBidAmount: raise.maxBidAmount },
      });
      return NextResponse.json(updated);
    }
    if (reservation.status !== "SCHEDULED") {
      return jsonError(409, "実行が始まっているため変更できません");
    }
    const body = await req.json();
    const data: { maxBidAmount?: number; snipeSecondsBefore?: number; dryRun?: boolean } &
      Partial<AutoRaiseFields> = {};
    // テスト実行の切り替えは実行前(SCHEDULED)のみ。
    // OFF にし忘れたまま終了時刻を迎えると実入札が飛ぶので、
    // 気づいた時点で ON に倒せるようにここで受ける。
    if (body.dryRun !== undefined) {
      data.dryRun = body.dryRun === true;
    }
    if (body.maxBidAmount !== undefined) {
      const v = Number(body.maxBidAmount);
      if (!Number.isInteger(v) || v <= (reservation.currentPrice ?? 0)) {
        return jsonError(400, "上限額は現在価格より高い整数で指定してください");
      }
      data.maxBidAmount = v;
    }
    if (body.snipeSecondsBefore !== undefined) {
      const v = Number(body.snipeSecondsBefore);
      if (!Number.isInteger(v) || v < SNIPE_SECONDS_MIN || v > SNIPE_SECONDS_MAX) {
        return jsonError(400, "実行タイミングの指定が不正です");
      }
      data.snipeSecondsBefore = v;
    }

    // 自動増額は上限額とセットで検証する。上限額だけ下げて絶対上限を据え置くと、
    // 「上限 < 絶対上限」の関係が崩れないまま予算だけ実質据え置きになる。
    if (
      body.autoRaiseMode !== undefined ||
      body.absoluteMaxAmount !== undefined ||
      body.autoRaiseStep !== undefined ||
      body.autoRaiseMaxCount !== undefined
    ) {
      const raise = validateAutoRaiseInput(body, data.maxBidAmount ?? reservation.maxBidAmount);
      if (!raise.ok) return jsonError(400, raise.error);
      if (raise.value.autoRaiseMode === "APPROVAL") {
        const notify = await prisma.notificationSetting.findUnique({
          where: { userId: user.id },
        });
        if (!notify?.telegramChatId) {
          return jsonError(
            400,
            "承認制の自動増額には Telegram の連携が必要です。設定 > 通知 で chat ID を登録してください",
          );
        }
      }
      Object.assign(data, raise.value);
    }

    // 締切判定は「変更前・変更後の遅いほう」で行う。変更前の値で monitor が
    // 既にキューへ入っている可能性があり、起動後の予約を書き換えても
    // ジョブ側は起動時に読んだ内容のまま走るため反映されない。
    const effectiveSnipe = Math.max(
      reservation.snipeSecondsBefore,
      data.snipeSecondsBefore ?? 0,
    );
    const remainingSec = Math.floor((reservation.endAt.getTime() - Date.now()) / 1000);
    if (remainingSec < editDeadlineSeconds(effectiveSnipe)) {
      return jsonError(409, `終了直前のため変更できません(終了まで残り${remainingSec}秒)`);
    }

    const updated = await prisma.bidReservation.update({
      where: { id: reservation.id },
      data,
    });
    return NextResponse.json(updated);
  });
}

/**
 * 予約のキャンセル。
 *
 * 受けるのは「まだ自分の入札が外に出ていない」あいだだけ(判定は cancelVerdict)。
 * 設計 §9 は「MONITORING 開始前まで」だったが、既定の実行秒数(330秒)だと
 * 終了の6分半前から押せなくなり、監視が始まったあと気が変わっても降りられない。
 * worker 側は monitor がループ先頭とスナイプ直前に予約を読み直して CANCELLED
 * なら降りるので(jobs/monitor.ts の syncReservation)、監視中の取り消しは
 * もともと成立する。ここが狭かっただけ。
 *
 * ⚠️ 状態の確認と更新のあいだに worker が BIDDING へ進む窓がある。
 * 読んだ結果で分岐して update すると、その隙にスナイプが始まった予約を
 * CANCELLED で塗りつぶす(入札は飛んだのに画面はキャンセル)。
 * だから最終的な書き込みは **status を where に入れた updateMany** で行い、
 * 0件なら断る。cancelVerdict は「なぜ駄目か」を言うためのもので、
 * 競合を防いでいるのはこの where。
 *
 * ⚠️ それでも、スナイプ直前の読み直しを過ぎてから入札が飛ぶまでの数秒は
 * 止められない。UI にその旨を書くこと。
 */
export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  return handle(async () => {
    const user = await requireUser();
    const reservation = await findOwned((await params).id, user.id);
    if (!reservation) return jsonError(404, "予約が見つかりません");

    const verdict = cancelVerdict({
      status: reservation.status,
      hasSuccessfulBid: reservation.attempts.some((a) => a.outcome === "SUCCESS"),
    });
    if (!verdict.ok) return jsonError(409, verdict.message);

    const res = await prisma.bidReservation.updateMany({
      where: { id: reservation.id, status: { in: ["SCHEDULED", "MONITORING"] } },
      data: { status: "CANCELLED" },
    });
    if (res.count === 0) {
      return jsonError(409, "入札処理が始まったためキャンセルできませんでした");
    }
    const updated = await prisma.bidReservation.findUnique({ where: { id: reservation.id } });
    return NextResponse.json(updated);
  });
}
