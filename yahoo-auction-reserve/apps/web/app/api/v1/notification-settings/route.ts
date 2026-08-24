import { NextResponse, type NextRequest } from "next/server";
import { prisma } from "@yar/db";
import { requireUser } from "@/lib/auth";
import { handle, jsonError } from "@/lib/api";

const HHMM = /^([01]\d|2[0-3]):([0-5]\d)$/;
/** リマインドの指定可能範囲(分)。24時間より前は予約直後に飛ぶだけで意味が薄い。 */
const REMIND_MIN = 1;
const REMIND_MAX = 24 * 60;
const REMIND_MAX_COUNT = 5;

export async function GET() {
  return handle(async () => {
    const user = await requireUser();
    const setting = await prisma.notificationSetting.findUnique({
      where: { userId: user.id },
    });
    return NextResponse.json(setting);
  });
}

export async function PUT(req: NextRequest) {
  return handle(async () => {
    const user = await requireUser();
    const body = await req.json();

    // 空文字と null を同じ「未設定」に寄せる。片方だけ通すと、消したつもりの
    // chat ID が空文字で残り、送信側の `if (chatId)` を通り抜けて 400 になる。
    const telegramChatId =
      typeof body.telegramChatId === "string" && body.telegramChatId.trim() !== ""
        ? body.telegramChatId.trim()
        : null;
    if (telegramChatId && !/^-?\d{1,20}$/.test(telegramChatId)) {
      return jsonError(400, "Telegram の chat ID は数字(グループなら先頭が -)で指定してください");
    }

    const raw: unknown[] = Array.isArray(body.remindMinutesBefore)
      ? body.remindMinutesBefore
      : [];
    const minutes: number[] = [...new Set(raw.map((v) => Number(v)))].sort((a, b) => b - a);
    if (minutes.length > REMIND_MAX_COUNT) {
      return jsonError(400, `リマインドは最大${REMIND_MAX_COUNT}件までです`);
    }
    for (const m of minutes) {
      if (!Number.isInteger(m) || m < REMIND_MIN || m > REMIND_MAX) {
        return jsonError(400, `リマインドは${REMIND_MIN}〜${REMIND_MAX}分前の範囲で指定してください`);
      }
    }

    const dailySummaryAt =
      typeof body.dailySummaryAt === "string" && body.dailySummaryAt.trim() !== ""
        ? body.dailySummaryAt.trim()
        : null;
    if (dailySummaryAt && !HHMM.test(dailySummaryAt)) {
      return jsonError(400, "稼働サマリの時刻は HH:MM(JST)で指定してください");
    }

    // Telegram 宛先が無いのにリマインドやサマリだけ有効にしても、メール設定が
    // 無ければどこにも届かない。ここは止めずに、画面側で注意書きを出す。
    const data = {
      telegramChatId,
      remindMinutesBefore: minutes,
      notifyResult: body.notifyResult !== false,
      notifyError: body.notifyError !== false,
      dailySummaryAt,
    };
    const saved = await prisma.notificationSetting.upsert({
      where: { userId: user.id },
      update: data,
      create: { userId: user.id, ...data },
    });
    return NextResponse.json(saved);
  });
}
