import { NextResponse } from "next/server";
import { prisma } from "@yar/db";
import { requireUser } from "@/lib/auth";
import { handle, jsonError } from "@/lib/api";

// 連携解除は物理削除(設計 §8)
export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  return handle(async () => {
    const user = await requireUser();
    const { id } = await params;
    const session = await prisma.yahooSession.findUnique({ where: { id } });
    if (!session || session.userId !== user.id) {
      return jsonError(404, "連携が見つかりません");
    }
    const active = await prisma.bidReservation.count({
      where: {
        yahooSessionId: id,
        status: { in: ["SCHEDULED", "MONITORING", "BIDDING"] },
      },
    });
    if (active > 0) {
      return jsonError(409, "この連携を使う実行前の予約があります。先に予約をキャンセルしてください");
    }
    await prisma.yahooSession.delete({ where: { id } });
    return NextResponse.json({ ok: true });
  });
}
