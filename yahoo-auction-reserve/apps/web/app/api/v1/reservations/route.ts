import { NextResponse, type NextRequest } from "next/server";
import { prisma } from "@yar/db";
import {
  EDIT_DEADLINE_SECONDS,
  SNIPE_SECONDS_DEFAULT,
  SNIPE_SECONDS_MAX,
  SNIPE_SECONDS_MIN,
  extractAuctionId,
  fetchAuctionInfo,
  normalizeAuctionUrl,
} from "@yar/shared";
import { requireUser } from "@/lib/auth";
import { handle, jsonError } from "@/lib/api";

export async function GET() {
  return handle(async () => {
    const user = await requireUser();
    const reservations = await prisma.bidReservation.findMany({
      where: { userId: user.id },
      orderBy: { endAt: "asc" },
    });
    return NextResponse.json(reservations);
  });
}

// 予約登録(設計 §9 のバリデーションを実装)
export async function POST(req: NextRequest) {
  return handle(async () => {
    const user = await requireUser();
    const body = await req.json();
    const { url, yahooSessionId } = body;
    const maxBidAmount = Number(body.maxBidAmount);
    const snipeSecondsBefore = Number(
      body.snipeSecondsBefore ?? SNIPE_SECONDS_DEFAULT,
    );

    const auctionId = typeof url === "string" ? extractAuctionId(url) : null;
    if (!auctionId) return jsonError(400, "ヤフオクの商品URLを入力してください");
    if (!Number.isInteger(maxBidAmount) || maxBidAmount <= 0) {
      return jsonError(400, "上限入札額を正しく入力してください");
    }
    if (
      !Number.isInteger(snipeSecondsBefore) ||
      snipeSecondsBefore < SNIPE_SECONDS_MIN ||
      snipeSecondsBefore > SNIPE_SECONDS_MAX
    ) {
      return jsonError(
        400,
        `実行タイミングは${SNIPE_SECONDS_MIN}〜${SNIPE_SECONDS_MAX}秒前の範囲で指定してください`,
      );
    }

    const session = await prisma.yahooSession.findUnique({
      where: { id: String(yahooSessionId ?? "") },
    });
    if (!session || session.userId !== user.id) {
      return jsonError(400, "ヤフオク連携を選択してください");
    }
    if (session.status !== "ACTIVE") {
      return jsonError(409, "選択したヤフオク連携が失効しています。再連携してください");
    }

    const duplicate = await prisma.bidReservation.findUnique({
      where: { userId_auctionId: { userId: user.id, auctionId } },
    });
    if (duplicate && !["CANCELLED", "FAILED", "LOST", "EXPIRED"].includes(duplicate.status)) {
      return jsonError(409, "この商品は既に予約済みです");
    }

    const info = await fetchAuctionInfo(normalizeAuctionUrl(auctionId));
    if (info.isClosed) return jsonError(400, "このオークションは既に終了しています");
    if (!info.endAt) {
      return jsonError(502, "終了日時を取得できませんでした。時間をおいて再度お試しください");
    }
    if (info.endAt.getTime() - Date.now() < EDIT_DEADLINE_SECONDS * 1000) {
      return jsonError(400, "終了直前のため予約できません(終了60秒前まで)");
    }
    if (info.currentPrice !== undefined && maxBidAmount <= info.currentPrice) {
      return jsonError(400, `上限額は現在価格(${info.currentPrice}円)より高くしてください`);
    }

    // 敗北済み等の過去予約が残っている場合は消してから作り直す(@@unique制約)
    if (duplicate) {
      await prisma.bidAttempt.deleteMany({ where: { reservationId: duplicate.id } });
      await prisma.bidReservation.delete({ where: { id: duplicate.id } });
    }

    const reservation = await prisma.bidReservation.create({
      data: {
        userId: user.id,
        yahooSessionId: session.id,
        auctionId,
        auctionUrl: normalizeAuctionUrl(auctionId),
        title: info.title ?? auctionId,
        imageUrl: info.imageUrl,
        sellerName: info.sellerName,
        hasAutoExtension: info.hasAutoExtension ?? false,
        endAt: info.endAt,
        originalEndAt: info.endAt,
        maxBidAmount,
        snipeSecondsBefore,
        currentPrice: info.currentPrice,
        priceCheckedAt: new Date(),
      },
    });
    return NextResponse.json(reservation, { status: 201 });
  });
}
