import { NextResponse, type NextRequest } from "next/server";
import bcrypt from "bcryptjs";
import { prisma } from "@yar/db";
import { canRegister } from "@yar/shared";
import { createSession } from "@/lib/auth";
import { handle, jsonError } from "@/lib/api";

export async function POST(req: NextRequest) {
  return handle(async () => {
    // ⚠️ 一番最初に閉店確認をする。入力チェックの後ろに置くと、
    // 「バリデーションを通った登録だけ通る」= 実質開いたままになる。
    const gate = canRegister({
      allowFlag: process.env.ALLOW_REGISTRATION,
      existingUserCount: await prisma.user.count(),
    });
    if (!gate.allowed) return jsonError(403, gate.reason ?? "新規登録は受け付けていません");

    const { email, password } = await req.json();
    if (typeof email !== "string" || !/^[^@\s]+@[^@\s]+$/.test(email)) {
      return jsonError(400, "メールアドレスの形式が不正です");
    }
    if (typeof password !== "string" || password.length < 8) {
      return jsonError(400, "パスワードは8文字以上にしてください");
    }
    const existing = await prisma.user.findUnique({ where: { email } });
    if (existing) return jsonError(409, "既に登録済みのメールアドレスです");

    const user = await prisma.user.create({
      data: { email, passwordHash: await bcrypt.hash(password, 12) },
    });
    await createSession(user.id);
    return NextResponse.json({ id: user.id, email: user.email }, { status: 201 });
  });
}
