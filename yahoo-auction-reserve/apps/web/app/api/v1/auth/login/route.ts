import { NextResponse, type NextRequest } from "next/server";
import bcrypt from "bcryptjs";
import { prisma } from "@yar/db";
import { createSession } from "@/lib/auth";
import { handle, jsonError } from "@/lib/api";
import {
  checkThrottle,
  clearFailures,
  clientIp,
  markFailure,
  throttleKeys,
} from "@/lib/loginThrottle";

export async function POST(req: NextRequest) {
  return handle(async () => {
    const { email, password } = await req.json();

    // ⚠️ 総当り対策は照合より前。「ユーザーが見つからない」の分岐より後ろに
    // 置くと、存在しないメールアドレスへの試行だけ無制限に通る。
    const keys = throttleKeys(email, clientIp(req.headers));
    const throttle = checkThrottle(keys);
    if (!throttle.allowed) {
      return jsonError(
        429,
        `ログインの試行が多すぎます。${throttle.retryAfterSec}秒後にもう一度お試しください`,
      );
    }

    const user =
      typeof email === "string"
        ? await prisma.user.findUnique({ where: { email } })
        : null;
    if (
      !user ||
      typeof password !== "string" ||
      !(await bcrypt.compare(password, user.passwordHash))
    ) {
      markFailure(keys);
      return jsonError(401, "メールアドレスまたはパスワードが違います");
    }
    clearFailures(keys);
    await createSession(user.id);
    return NextResponse.json({ id: user.id, email: user.email });
  });
}
