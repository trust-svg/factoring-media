import { NextResponse, type NextRequest } from "next/server";
import { prisma } from "@yar/db";
import {
  editDeadlineSeconds,
  SNIPE_SECONDS_MAX,
  SNIPE_SECONDS_MIN,
  validateAutoRaiseInput,
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
    if (reservation.status !== "SCHEDULED") {
      return jsonError(409, "実行が始まっているため変更できません");
    }
    const body = await req.json();
    const data: { maxBidAmount?: number; snipeSecondsBefore?: number } &
      Partial<AutoRaiseFields> = {};
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

// キャンセルは MONITORING 開始前まで(設計 §9)
export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  return handle(async () => {
    const user = await requireUser();
    const reservation = await findOwned((await params).id, user.id);
    if (!reservation) return jsonError(404, "予約が見つかりません");
    if (reservation.status !== "SCHEDULED") {
      return jsonError(409, "実行が始まっているためキャンセルできません");
    }
    const updated = await prisma.bidReservation.update({
      where: { id: reservation.id },
      data: { status: "CANCELLED" },
    });
    return NextResponse.json(updated);
  });
}
