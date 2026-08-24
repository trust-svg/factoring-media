import { NextResponse, type NextRequest } from "next/server";
import { prisma } from "@yar/db";
import { requireUser } from "@/lib/auth";
import { handle, jsonError } from "@/lib/api";

// 「予約しない」の伏せ操作。行は消さずに dismissedAt を立てるだけにする。
// 消すと次の同期でそのまま復活し、伏せた意味が無くなる。
export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  return handle(async () => {
    const user = await requireUser();
    const id = (await params).id;
    const item = await prisma.watchlistItem.findUnique({ where: { id } });
    if (!item || item.userId !== user.id) return jsonError(404, "見つかりません");
    const updated = await prisma.watchlistItem.update({
      where: { id },
      data: { dismissedAt: new Date() },
    });
    return NextResponse.json(updated);
  });
}
