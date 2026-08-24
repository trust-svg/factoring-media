import { NextResponse, type NextRequest } from "next/server";
import { prisma } from "@yar/db";
import {
  CookieParseError,
  encryptSecret,
  normalizeYahooCookies,
  parseCookieInput,
} from "@yar/shared";
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
    const body = await req.json();
    const { label, cookies, cookiesJson } = body;

    if (typeof label !== "string" || label.length === 0 || label.length > 50) {
      return jsonError(400, "ラベルは1〜50文字で入力してください");
    }

    // 貼り付けテキスト(cookiesJson)と配列(cookies)の両方を受ける。
    // 形式の揺れ(Cookie-Editor / storageState / 素の配列)は shared 側で吸収する。
    let normalized;
    try {
      const raw =
        typeof cookiesJson === "string" ? parseCookieInput(cookiesJson) : cookies;
      normalized = normalizeYahooCookies(raw);
    } catch (err) {
      if (err instanceof CookieParseError) {
        return jsonError(400, `Cookieを読み取れませんでした: ${err.message}`);
      }
      throw err;
    }

    const session = await prisma.yahooSession.create({
      data: {
        userId: user.id,
        label,
        encryptedCookie: encryptSecret(JSON.stringify(normalized.cookies)),
      },
      select: { id: true, label: true, status: true, createdAt: true },
    });
    // TODO(P1): 登録直後の有効性チェック(実リクエストでのログイン判定)は
    // P0 検証でログイン判定方法を確定させてから worker 側に実装する。
    // 現時点では「必要な Cookie 名が揃っているか」の構造チェックのみ(warnings)。
    return NextResponse.json(
      { ...session, cookieCount: normalized.cookies.length, warnings: normalized.warnings },
      { status: 201 },
    );
  });
}
