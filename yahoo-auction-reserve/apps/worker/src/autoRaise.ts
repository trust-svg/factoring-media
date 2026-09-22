import { prisma, type BidReservation } from "@yar/db";
import {
  decideRaise,
  editDeadlineSeconds,
  minimumBidToBeat,
  type AutoRaiseConfig,
} from "@yar/shared";
import { notifyUser } from "./notify";
import { editTelegramMessage, escapeHtml, sendTelegram, telegramEnabled } from "./telegram";
import { yahooNow } from "./time";

// 高値更新されたときの増額フロー(設計追補 2026-08-25)。
//
// 承認制は **入札直前ではなく価格更新の時点で聞く**。入札直前(T-30秒など)に
// 聞いても人間が答える時間が無く、実質いつも TIMEOUT になる。refresh は
// 30分/5分間隔で回っているので、そこで気づいた時点で聞けば猶予が取れる。
//
// 承認の期限は「予約内容を変更しても入札に反映される最後の時刻」= 編集締切。
// これを過ぎたら TIMEOUT にして **元の額のまま入札する**。
// 承認が取れなかったことを増額の許可に読み替えない。

export type RaiseOutcome =
  | { kind: "RAISED"; newAmount: number }
  | { kind: "APPROVAL_PENDING"; approvalId: string }
  | { kind: "DECLINED"; reason: string; message: string };

function configOf(r: BidReservation): AutoRaiseConfig {
  return {
    mode: r.autoRaiseMode,
    step: r.autoRaiseStep,
    maxCount: r.autoRaiseMaxCount,
    usedCount: r.autoRaiseUsedCount,
    absoluteMax: r.absoluteMaxAmount,
  };
}

const DECLINE_MESSAGE: Record<string, string> = {
  MODE_OFF: "自動増額は設定されていません",
  COUNT_EXHAUSTED: "自動増額の回数上限に達しています",
  AT_CEILING: "絶対上限に達しているため増額できません",
  MISCONFIGURED: "自動増額の設定が不完全です(上限額・増額幅・回数のいずれかが未設定)",
  BELOW_REQUIRED: "絶対上限まで引き上げても現在価格を上回れません",
  NO_TIME: "承認を待つ時間が残っていないため増額しませんでした",
  APPROVAL_UNAVAILABLE: "Telegram の宛先が未設定のため承認を求められませんでした",
  ALREADY_PENDING: "同じ予約の承認待ちが既にあります",
};

function declined(reason: string): RaiseOutcome {
  return { kind: "DECLINED", reason, message: DECLINE_MESSAGE[reason] ?? reason };
}

/**
 * 高値更新に対して増額を試みる。
 *
 * `allowApproval` が false のときは承認制の予約でも問い合わせを行わない
 * (入札直前など、返事を待てない場面で使う)。
 */
export async function tryAutoRaise(
  reservation: BidReservation,
  currentPrice: number,
  opts: { allowApproval: boolean },
): Promise<RaiseOutcome> {
  const required = minimumBidToBeat(currentPrice);
  const decision = decideRaise(reservation.maxBidAmount, configOf(reservation), required);
  if (!decision.raise) return declined(decision.reason);

  if (!decision.needsApproval) {
    return applyRaise(reservation, decision.nextAmount, currentPrice);
  }
  if (!opts.allowApproval) return declined("NO_TIME");

  // 承認を待てる最終時刻 = 編集締切。ここを過ぎると変更が入札に載らない
  const deadline = new Date(
    reservation.endAt.getTime() - editDeadlineSeconds(reservation.snipeSecondsBefore) * 1000,
  );
  if (deadline.getTime() <= yahooNow().getTime()) return declined("NO_TIME");

  const setting = await prisma.notificationSetting.findUnique({
    where: { userId: reservation.userId },
  });
  const chatId = setting?.telegramChatId;
  if (!chatId || !telegramEnabled()) return declined("APPROVAL_UNAVAILABLE");

  // 同じ予約の PENDING が残っているなら重ねて聞かない。
  // 聞くたびにボタン付きメッセージが増えると、古いボタンを押されたときに
  // どの金額に対する承認なのか分からなくなる。
  const pending = await prisma.telegramApproval.findFirst({
    where: { reservationId: reservation.id, status: "PENDING" },
  });
  if (pending) return declined("ALREADY_PENDING");

  const approval = await prisma.telegramApproval.create({
    data: {
      reservationId: reservation.id,
      currentAmount: reservation.maxBidAmount,
      requestedAmount: decision.nextAmount,
      chatId,
      expiresAt: deadline,
    },
  });

  const html = [
    "<b>【承認待ち】増額してよいですか</b>",
    "",
    escapeHtml(reservation.title ?? reservation.auctionUrl),
    `現在価格: ¥${currentPrice.toLocaleString("ja-JP")}`,
    `今の入札額: ¥${reservation.maxBidAmount.toLocaleString("ja-JP")}`,
    `増額後: <b>¥${decision.nextAmount.toLocaleString("ja-JP")}</b>`,
    `絶対上限: ¥${(reservation.absoluteMaxAmount ?? 0).toLocaleString("ja-JP")}`,
    "",
    `回答期限: ${deadline.toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" })}`,
    "期限までに返事が無いときは<b>増額せず、元の額のまま</b>入札します。",
  ].join("\n");

  try {
    const sent = await sendTelegram(chatId, html, [
      { text: `承認 ¥${decision.nextAmount.toLocaleString("ja-JP")}`, callbackData: `ar:${approval.id}:y` },
      { text: "却下", callbackData: `ar:${approval.id}:n` },
    ]);
    await prisma.telegramApproval.update({
      where: { id: approval.id },
      data: { messageId: sent.messageId },
    });
  } catch (err) {
    // 送れていないのに PENDING のまま置くと、期限まで「返事待ち」に見えて
    // 増額の機会を無言で捨てる。送信失敗はその場で TIMEOUT に倒す。
    await prisma.telegramApproval.update({
      where: { id: approval.id },
      data: { status: "TIMEOUT", respondedAt: new Date() },
    });
    console.error(`[autoRaise] 承認依頼の送信に失敗 ${approval.id}:`, err);
    return declined("APPROVAL_UNAVAILABLE");
  }

  await notifyUser(reservation.userId, "APPROVAL_REQUEST", {
    title: reservation.title,
    url: reservation.auctionUrl,
    currentPrice,
    maxBidAmount: reservation.maxBidAmount,
    nextAmount: decision.nextAmount,
  });
  return { kind: "APPROVAL_PENDING", approvalId: approval.id };
}

/**
 * 増額を実際に反映する。
 *
 * refresh・monitor・承認ポーラの3経路から呼ばれうるので、
 * 「読んだときの値と同じままか」を条件にした更新にして二重増額を防ぐ。
 * 単に increment すると、同時に走った2経路が両方成功して step の2倍上がる。
 */
export async function applyRaise(
  reservation: BidReservation,
  nextAmount: number,
  currentPrice: number | null,
): Promise<RaiseOutcome> {
  const updated = await prisma.bidReservation.updateMany({
    where: {
      id: reservation.id,
      maxBidAmount: reservation.maxBidAmount,
      autoRaiseUsedCount: reservation.autoRaiseUsedCount,
      status: { in: ["SCHEDULED", "MONITORING", "BIDDING"] },
    },
    data: {
      maxBidAmount: nextAmount,
      autoRaiseUsedCount: { increment: 1 },
      // 上限超過でスキップ済みだった場合はスケジュールへ戻す
      status: "SCHEDULED",
      failureReason: null,
    },
  });
  if (updated.count === 0) {
    return declined("ALREADY_PENDING"); // 別経路が先に上げた / 状態が変わった
  }

  await prisma.bidAttempt.create({
    data: {
      reservationId: reservation.id,
      scheduledFor: yahooNow(),
      executedAt: yahooNow(),
      bidAmount: nextAmount,
      outcome: "AUTO_RAISED",
      detail: `¥${reservation.maxBidAmount.toLocaleString("ja-JP")} → ¥${nextAmount.toLocaleString("ja-JP")}${
        currentPrice != null ? ` (現在価格 ¥${currentPrice.toLocaleString("ja-JP")})` : ""
      }`,
    },
  });

  await notifyUser(reservation.userId, "AUTO_RAISED", {
    title: reservation.title,
    url: reservation.auctionUrl,
    currentPrice: currentPrice ?? undefined,
    maxBidAmount: reservation.maxBidAmount,
    nextAmount,
    absoluteMaxAmount: reservation.absoluteMaxAmount ?? undefined,
  });
  return { kind: "RAISED", newAmount: nextAmount };
}

/**
 * 期限を過ぎた PENDING を TIMEOUT にする。
 *
 * ボタンが押されなかったことを検知する能動的な掃除。受動的な
 * 「押されたら処理する」だけにすると、押されなかった承認は PENDING のまま
 * 残り続け、次の増額機会が ALREADY_PENDING で永久に塞がれる。
 */
export async function expireStaleApprovals(): Promise<number> {
  const stale = await prisma.telegramApproval.findMany({
    where: { status: "PENDING", expiresAt: { lte: new Date() } },
    include: { reservation: true },
  });
  for (const a of stale) {
    await prisma.telegramApproval.update({
      where: { id: a.id },
      data: { status: "TIMEOUT", respondedAt: new Date() },
    });
    await recordDecline(a.reservationId, "承認の期限切れ(元の額のまま入札します)");
    if (a.chatId && a.messageId && telegramEnabled()) {
      await editApprovalMessage(a.chatId, a.messageId, "⏰ 期限切れ — 増額せず、元の額のまま入札します").catch(
        (err) => console.error(`[autoRaise] 期限切れ表示の更新に失敗 ${a.id}:`, err),
      );
    }
  }
  return stale.length;
}

export async function recordDecline(reservationId: string, detail: string): Promise<void> {
  const r = await prisma.bidReservation.findUnique({ where: { id: reservationId } });
  if (!r) return;
  await prisma.bidAttempt.create({
    data: {
      reservationId,
      scheduledFor: yahooNow(),
      executedAt: yahooNow(),
      bidAmount: r.maxBidAmount,
      outcome: "RAISE_DECLINED",
      detail,
    },
  });
  await notifyUser(r.userId, "RAISE_DECLINED", {
    title: r.title,
    url: r.auctionUrl,
    maxBidAmount: r.maxBidAmount,
    reason: detail,
  });
}

function editApprovalMessage(chatId: string, messageId: number, text: string): Promise<void> {
  return editTelegramMessage(chatId, messageId, escapeHtml(text));
}
