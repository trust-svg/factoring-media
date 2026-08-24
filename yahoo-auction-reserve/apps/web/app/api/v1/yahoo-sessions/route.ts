import { NextResponse, type NextRequest } from "next/server";
import { prisma } from "@yar/db";
import { encryptSecret, type YahooCookie } from "@yar/shared";
import { requireUser } from "@/lib/auth";
import { handle, jsonError } from "@/lib/api";

// Cookie本体は絶対にレスポンスへ含めない(設計 §8, §9)
export async function GET() {
  return handle(async () => {
    const user = await requireUser();
    const sessions = await prisma.yahooSession.findMany({
      where: { userId: user.id },
      select: {
        id: true,
        label: true,
        status: true,
        lastVerifiedAt: true,
        createdAt: true,
      },
      orderBy: { createdAt: "desc" },
    });
    return NextResponse.json(sessions);
  });
}

export async function POST(req: NextRequest) {
  return handle(async () => {
    const user = await requireUser();
    const { label, cookies } = await req.json();

    if (typeof label !== "string" || label.length === 0 || label.length > 50) {
      return jsonError(400, "ラベルは1〜50文字で入力してください");
    }
    if (!Array.isArray(cookies) || cookies.length === 0) {
      return jsonError(400, "Cookieが空です。連携手順に沿って取得してください");
    }
    const valid = cookies.every(
      (c: Partial<YahooCookie>) =>
        typeof c?.name === "string" &&
        typeof c?.value === "string" &&
        typeof c?.domain === "string" &&
        c.domain.endsWith("yahoo.co.jp"),
    );
    if (!valid) {
      return jsonError(400, "Cookieの形式が不正です(yahoo.co.jp ドメインのみ登録できます)");
    }

    const session = await prisma.yahooSession.create({
      data: {
        userId: user.id,
        label,
        encryptedCookie: encryptSecret(JSON.stringify(cookies)),
      },
      select: { id: true, label: true, status: true, createdAt: true },
    });
    // TODO(P1): 登録直後の有効性チェックを worker に依頼し、結果を status に反映する
    return NextResponse.json(session, { status: 201 });
  });
}
