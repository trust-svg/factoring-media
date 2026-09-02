import { NextResponse, type NextRequest } from "next/server";
import { prisma } from "@yar/db";
import {
  editDeadlineSeconds,
  SNIPE_SECONDS_DEFAULT,
  SNIPE_SECONDS_MAX,
  SNIPE_SECONDS_MIN,
  extractAuctionId,
  fetchAuctionInfo,
  judgeSeller,
  normalizeAuctionUrl,
  validateAutoRaiseInput,
} from "@yar/shared";
import { isRebookableReservation } from "@yar/shared/labels";
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

    const raise = validateAutoRaiseInput(body, maxBidAmount);
    if (!raise.ok) return jsonError(400, raise.error);
    // 承認制は Telegram の宛先が無いと「承認依頼を送れない = 一度も増額しない」に
    // なる。設定として保存はできてしまうので、ここで断らないと無言で効かない。
    if (raise.value.autoRaiseMode === "APPROVAL") {
      const notify = await prisma.notificationSetting.findUnique({
        where: { userId: user.id },
      });
      if (!notify?.telegramChatId) {
        return jsonError(
          400,
          "承認制の自動増額には Telegram の連携が必要です。設定 > 通知 で chat ID を登録してください",
        );
      }
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
    // 終了済みの予約は再登録を許す(判定は @yar/shared/labels に集約。
    // ウォッチリスト画面と同じ一覧を使わないと、API は許すのに画面からは
    // 二度と予約できない状態になる)。
    if (duplicate && !isRebookableReservation(duplicate.status)) {
      return jsonError(409, "この商品は既に予約済みです");
    }

    const info = await fetchAuctionInfo(normalizeAuctionUrl(auctionId));
    if (info.isClosed) return jsonError(400, "このオークションは既に終了しています");
    if (!info.endAt) {
      return jsonError(502, "終了日時を取得できませんでした。時間をおいて再度お試しください");
    }
    // 締切は実行タイミングによって変わる。「終了600秒前に入札」は残り3分の
    // 商品では原理的に成立しないので、黙って直前入札にせずここで断る。
    const remainingSec = Math.floor((info.endAt.getTime() - Date.now()) / 1000);
    const deadline = editDeadlineSeconds(snipeSecondsBefore);
    if (remainingSec < deadline) {
      // 準備に要する固定分を引いた、いま指定できる最大の実行タイミング
      const usable = remainingSec - (deadline - snipeSecondsBefore);
      return jsonError(
        400,
        usable >= SNIPE_SECONDS_MIN
          ? `終了まで残り${remainingSec}秒です。実行タイミングを${usable}秒前以下にすれば予約できます`
          : `終了が近すぎるため予約できません(終了まで残り${remainingSec}秒)`,
      );
    }
    if (info.currentPrice !== undefined && maxBidAmount <= info.currentPrice) {
      return jsonError(400, `上限額は現在価格(${info.currentPrice}円)より高くしてください`);
    }

    // 出品者の足切り。しきい値を設定していないユーザーには何も起きない。
    // 「取得できなかった(unknown)」で断らないのは、パーサが壊れた日に
    // 全予約が登録不能になるため(警告として画面に出す方に倒す)。
    const seller = judgeSeller(
      {
        sellerRating: info.sellerRating ?? null,
        sellerRatingCount: info.sellerRatingCount ?? null,
      },
      {
        sellerRatingFloor: user.sellerRatingFloor,
        sellerRatingMinCount: user.sellerRatingMinCount,
      },
    );
    if (seller.level === "warn" && user.blockLowRatedSeller) {
      return jsonError(
        409,
        `出品者の足切り条件に該当します(${seller.reasons.join(" / ")})。設定 > 判断材料 で変更できます`,
      );
    }

    // グループは「どれか1つ落札したら残りを取りやめる」束。他人のグループに
    // 紐付けられないよう所有者を確認する。
    let groupId: string | null = null;
    if (typeof body.groupId === "string" && body.groupId) {
      const group = await prisma.reservationGroup.findUnique({
        where: { id: body.groupId },
      });
      if (!group || group.userId !== user.id) {
        return jsonError(400, "指定されたグループが見つかりません");
      }
      groupId = group.id;
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
        buyNowPrice: info.buyNowPrice ?? null,
        priceCheckedAt: new Date(),
        shippingFee: info.shippingFee ?? null,
        shippingNote: info.shippingNote ?? null,
        sellerRating: info.sellerRating ?? null,
        sellerRatingCount: info.sellerRatingCount ?? null,
        groupId,
        // テスト実行。確定クリックだけを行わず、それ以外は本番と同じ経路を通す。
        // 明示的に true を送ったときだけ有効(未指定は本番実行)。
        dryRun: body.dryRun === true,
        ...raise.value,
      },
    });
    return NextResponse.json(reservation, { status: 201 });
  });
}
