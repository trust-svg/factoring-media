import { NextResponse, type NextRequest } from "next/server";
import { prisma } from "@yar/db";
import { requireUser } from "@/lib/auth";
import { handle, jsonError } from "@/lib/api";

const NAME_MAX = 40;

export async function GET() {
  return handle(async () => {
    const user = await requireUser();
    const groups = await prisma.reservationGroup.findMany({
      where: { userId: user.id },
      orderBy: { createdAt: "desc" },
      include: { _count: { select: { reservations: true } } },
    });
    return NextResponse.json(groups);
  });
}

// グループ = 「どれか1つ落札したら残りを取りやめる」束(設計 §6)。
export async function POST(req: NextRequest) {
  return handle(async () => {
    const user = await requireUser();
    const body = await req.json();
    const name = typeof body.name === "string" ? body.name.trim() : "";
    if (!name) return jsonError(400, "グループ名を入力してください");
    if (name.length > NAME_MAX) {
      return jsonError(400, `グループ名は${NAME_MAX}文字以内で入力してください`);
    }
    const group = await prisma.reservationGroup.create({
      data: {
        userId: user.id,
        name,
        // 既定は true。false にするとただのラベルになる(取りやめない)。
        cancelOthersOnWin: body.cancelOthersOnWin !== false,
      },
    });
    return NextResponse.json(group, { status: 201 });
  });
}
