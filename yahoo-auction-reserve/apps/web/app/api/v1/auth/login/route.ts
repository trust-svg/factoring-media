import { NextResponse, type NextRequest } from "next/server";
import bcrypt from "bcryptjs";
import { prisma } from "@yar/db";
import { createSession } from "@/lib/auth";
import { handle, jsonError } from "@/lib/api";

export async function POST(req: NextRequest) {
  return handle(async () => {
    const { email, password } = await req.json();
    const user =
      typeof email === "string"
        ? await prisma.user.findUnique({ where: { email } })
        : null;
    if (
      !user ||
      typeof password !== "string" ||
      !(await bcrypt.compare(password, user.passwordHash))
    ) {
      return jsonError(401, "メールアドレスまたはパスワードが違います");
    }
    await createSession(user.id);
    return NextResponse.json({ id: user.id, email: user.email });
  });
}
