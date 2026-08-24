import { NextResponse, type NextRequest } from "next/server";
import { prisma } from "@yar/db";
import {
  EDIT_DEADLINE_SECONDS,
  SNIPE_SECONDS_MAX,
  SNIPE_SECONDS_MIN,
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
    if (reservation.endAt.getTime() - Date.now() < EDIT_DEADLINE_SECONDS * 1000) {
      return jsonError(409, "終了直前のため変更できません");
    }

    const body = await req.json();
    const data: { maxBidAmount?: number; snipeSecondsBefore?: number } = {};
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
