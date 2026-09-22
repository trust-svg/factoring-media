import { prisma } from "@yar/db";
import { minimumBidToBeat } from "@yar/shared";
import {
  TelegramError,
  answerCallbackQuery,
  editTelegramMessage,
  escapeHtml,
  nextOffset,
  pollCallbacks,
  telegramEnabled,
  type CallbackUpdate,
} from "./telegram";
import { applyRaise, expireStaleApprovals, recordDecline } from "./autoRaise";
import { sleep } from "./time";

// 増額承認ボタンの受け口(long polling)。
//
// ⚠️ getUpdates は 1 Bot につき 1 消費者しか許されない。worker を複数
// 立てると片方が 409 を受け続け、**ボタンだけが無言で効かなくなる**
// (通知は両方から出るので、一見すると正常に見える)。409 は必ず警告に出す。
//
// ⚠️ webhook を設定している Bot でも getUpdates は 409 になる。
// この Bot は本アプリ専用にすること。

const CALLBACK_PREFIX = "ar";

export function startApprovalPoller(): { stop: () => void } {
  if (!telegramEnabled()) {
    console.log("[approval] TELEGRAM_BOT_TOKEN が無いため承認ポーラは起動しません");
    return { stop: () => {} };
  }

  let running = true;
  // 未処理の update だけを取りに行く。0 から始めると再起動時に
  // Telegram 側に残っている古い押下(既に期限切れのもの)まで拾ってしまう。
  // 期限切れは resolveApproval 側で弾く。
  let offset = 0;

  void (async () => {
    while (running) {
      try {
        const updates = await pollCallbacks(offset);
        offset = nextOffset(updates, offset);
        for (const u of updates) {
          try {
            await handleCallback(u);
          } catch (err) {
            // 1件の失敗で以降の押下を捨てない。捨てると offset だけ進んで
            // その承認は永久に未処理のまま期限切れになる。
            console.error(`[approval] callback ${u.updateId} の処理に失敗:`, err);
          }
        }
      } catch (err) {
        if (err instanceof TelegramError && err.statusCode === 409) {
          console.error(
            "[approval] getUpdates が 409。この Bot を別の worker か webhook が使っています。" +
              "承認ボタンは動きません(通知は出るので気づきにくい)。",
          );
        } else {
          console.error("[approval] ポーリングに失敗:", err);
        }
        await sleep(10_000);
      }
    }
  })();

  return {
    stop: () => {
      running = false;
    },
  };
}

async function handleCallback(u: CallbackUpdate): Promise<void> {
  const parts = u.data.split(":");
  if (parts[0] !== CALLBACK_PREFIX || parts.length !== 3) return;
  const [, approvalId, verdict] = parts;
  if (!approvalId || (verdict !== "y" && verdict !== "n")) return;

  const approval = await prisma.telegramApproval.findUnique({
    where: { id: approvalId },
    include: { reservation: true },
  });
  if (!approval) {
    await answerCallbackQuery(u.callbackQueryId, "この承認は見つかりません");
    return;
  }

  // 押した相手が依頼先と同じ chat か確認する。転送されたメッセージからでも
  // ボタンは押せるので、chat が違えば金額を動かす操作は通さない。
  if (approval.chatId && approval.chatId !== u.chatId) {
    await answerCallbackQuery(u.callbackQueryId, "この承認には応答できません");
    console.warn(`[approval] 別 chat からの応答を無視 approval=${approvalId}`);
    return;
  }

  if (approval.status !== "PENDING") {
    await answerCallbackQuery(u.callbackQueryId, "この承認は既に処理済みです");
    await editTelegramMessage(
      u.chatId,
      u.messageId,
      escapeHtml(`処理済み(${approval.status})`),
    ).catch(() => {});
    return;
  }

  if (approval.expiresAt.getTime() <= Date.now()) {
    await prisma.telegramApproval.update({
      where: { id: approval.id },
      data: { status: "TIMEOUT", respondedAt: new Date() },
    });
    await answerCallbackQuery(u.callbackQueryId, "期限切れです");
    await editTelegramMessage(
      u.chatId,
      u.messageId,
      escapeHtml("⏰ 期限切れ — 増額せず、元の額のまま入札します"),
    ).catch(() => {});
    await recordDecline(approval.reservationId, "承認の期限切れ(元の額のまま入札します)");
    return;
  }

  if (verdict === "n") {
    await prisma.telegramApproval.update({
      where: { id: approval.id },
      data: { status: "REJECTED", respondedAt: new Date() },
    });
    await answerCallbackQuery(u.callbackQueryId, "却下しました");
    await editTelegramMessage(
      u.chatId,
      u.messageId,
      escapeHtml("❌ 却下 — 増額せず、元の額のまま入札します"),
    ).catch(() => {});
    await recordDecline(approval.reservationId, "ユーザーが増額を却下しました");
    return;
  }

  // 承認。依頼したときの金額をそのまま使う(ボタンに書いてある額と
  // 実際に出す額をズラさない)。ただし承認を待つ間に相場が上がっている
  // ことはあるので、足りなければ「足りない」と伝えて終える。
  const r = approval.reservation;
  await prisma.telegramApproval.update({
    where: { id: approval.id },
    data: { status: "APPROVED", respondedAt: new Date() },
  });

  const price = r.currentPrice;
  if (price != null && approval.requestedAmount < minimumBidToBeat(price)) {
    await answerCallbackQuery(u.callbackQueryId, "承認額では現在価格を上回れません");
    await editTelegramMessage(
      u.chatId,
      u.messageId,
      escapeHtml(
        `⚠️ 承認しましたが、その後の高値更新(¥${price.toLocaleString("ja-JP")})により` +
          `¥${approval.requestedAmount.toLocaleString("ja-JP")}では上回れないため増額しません`,
      ),
    ).catch(() => {});
    await recordDecline(
      approval.reservationId,
      "承認を待つ間に価格が上がり、承認額では上回れなくなりました",
    );
    return;
  }

  const outcome = await applyRaise(r, approval.requestedAmount, price);
  await answerCallbackQuery(
    u.callbackQueryId,
    outcome.kind === "RAISED" ? "増額しました" : "反映できませんでした",
  );
  await editTelegramMessage(
    u.chatId,
    u.messageId,
    escapeHtml(
      outcome.kind === "RAISED"
        ? `✅ 承認 — ¥${outcome.newAmount.toLocaleString("ja-JP")}へ増額しました`
        : "⚠️ 承認しましたが、予約の状態が変わっていたため反映できませんでした",
    ),
  ).catch(() => {});
}

/** 期限切れ掃除。呼び出し側(スケジューラ)から定期的に叩く */
export async function sweepApprovals(): Promise<void> {
  const n = await expireStaleApprovals();
  if (n > 0) console.log(`[approval] 期限切れ ${n} 件を TIMEOUT にしました`);
}
