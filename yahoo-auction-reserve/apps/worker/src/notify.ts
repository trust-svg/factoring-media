import nodemailer from "nodemailer";
import { Prisma, prisma } from "@yar/db";
import { NOTIFICATION_CATEGORY, type NotificationType } from "@yar/shared";
import { escapeHtml, sendTelegram, telegramEnabled } from "./telegram";

const transporter = process.env.SMTP_HOST
  ? nodemailer.createTransport({
      host: process.env.SMTP_HOST,
      port: Number(process.env.SMTP_PORT ?? 587),
      auth: process.env.SMTP_USER
        ? { user: process.env.SMTP_USER, pass: process.env.SMTP_PASS }
        : undefined,
    })
  : null;

// 型を Record<NotificationType, string> にしているのは、NotificationType を
// 増やしたときにここが必ずコンパイルエラーになるようにするため。
// 既定値つきの参照にすると、件名だけ古いまま新しい通知が出続ける。
const SUBJECTS: Record<NotificationType, string> = {
  WON: "【落札成功】入札予約が落札されました",
  LOST: "【落札ならず】高値更新されました",
  FAILED: "【要確認】入札の実行に失敗しました",
  EXPIRED: "【スキップ】現在価格が上限額を超えました",
  SESSION_EXPIRED: "【要対応】ヤフオク連携が切れています",
  REMINDER: "【まもなく終了】入札予約の終了が近づいています",
  AUTO_RAISED: "【自動増額】上限を引き上げて入札しなおしました",
  RAISE_DECLINED: "【増額せず】上限を引き上げられませんでした",
  APPROVAL_REQUEST: "【承認待ち】増額してよいか確認しています",
  GROUP_CANCELLED: "【取りやめ】同じグループの他の商品を落札しました",
  DAILY_SUMMARY: "【稼働サマリ】入札予約の状況",
  DRY_RUN: "【テスト実行】確認画面まで到達しました(入札はしていません)",
};

// payload のキーをそのまま出すと "maxBidAmount: 6000" のような画面になるので、
// 分かっているものだけ日本語にする(未知のキーはキー名のまま出す)。
const FIELD_LABELS: Record<string, string> = {
  title: "商品",
  url: "URL",
  currentPrice: "現在価格",
  finalPrice: "落札価格",
  maxBidAmount: "入札額",
  absoluteMaxAmount: "絶対上限",
  nextAmount: "増額後の入札額",
  reason: "理由",
  hint: "対応",
  endAt: "終了時刻",
  minutesBefore: "終了まで",
  groupName: "グループ",
  detail: "結果",
  lateBySec: "予定との差",
};

/** payload の "_lines" は見出しを付けずそのまま並べる(サマリ用) */
function renderLines(payload: Record<string, unknown>): string[] {
  const out: string[] = [];
  for (const [k, v] of Object.entries(payload)) {
    if (v === undefined || v === null || v === "") continue;
    if (k === "_lines" && Array.isArray(v)) {
      out.push(...v.map(String));
      continue;
    }
    out.push(`${FIELD_LABELS[k] ?? k}: ${String(v)}`);
  }
  return out;
}

export interface NotifyResult {
  mailSent: boolean;
  telegramSent: boolean;
  /** どの経路も送れなかった理由。両方無効な設定のときは null(失敗ではない) */
  error: string | null;
}

export async function notifyUser(
  userId: string,
  type: NotificationType,
  payload: Record<string, unknown>,
): Promise<NotifyResult> {
  const notification = await prisma.notification.create({
    data: { userId, type, payload: payload as Prisma.InputJsonObject },
  });

  const user = await prisma.user.findUnique({
    where: { id: userId },
    include: { notifySetting: true },
  });
  if (!user) return { mailSent: false, telegramSent: false, error: "ユーザーが存在しません" };

  const setting = user.notifySetting;
  const category = NOTIFICATION_CATEGORY[type];
  // ユーザーが切れるのは RESULT / ERROR だけ。ACTION(承認依頼)と SUMMARY は
  // 切れない。承認依頼が届かないことは「増額しない」という実害に直結する。
  if (category === "RESULT" && setting && !setting.notifyResult) {
    return { mailSent: false, telegramSent: false, error: null };
  }
  if (category === "ERROR" && setting && !setting.notifyError) {
    return { mailSent: false, telegramSent: false, error: null };
  }

  const subject = SUBJECTS[type];
  const lines = renderLines(payload);
  const text = [subject, "", ...lines].join("\n");
  const html = [`<b>${escapeHtml(subject)}</b>`, "", ...lines.map(escapeHtml)].join("\n");

  const errors: string[] = [];
  let mailSentAt: Date | null = null;
  let telegramSentAt: Date | null = null;

  if (transporter) {
    try {
      await transporter.sendMail({
        from: process.env.MAIL_FROM ?? "no-reply@localhost",
        to: user.email,
        subject,
        text,
      });
      mailSentAt = new Date();
    } catch (err) {
      errors.push(`mail: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  const chatId = setting?.telegramChatId;
  if (chatId && telegramEnabled()) {
    try {
      await sendTelegram(chatId, html);
      telegramSentAt = new Date();
    } catch (err) {
      // TelegramError 側でトークンは除去済み
      errors.push(`telegram: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  const error = errors.length ? errors.join(" / ") : null;
  await prisma.notification.update({
    where: { id: notification.id },
    data: { mailSentAt, telegramSentAt, deliveryError: error },
  });

  if (!transporter && !chatId) {
    // 経路が1つも無い開発環境では、黙って捨てずにログへ出す
    console.log(`[notify] (経路なし) to=${user.email}\n${text}`);
  }
  if (error) console.error(`[notify] ${type} の送信に失敗 user=${userId}: ${error}`);

  return { mailSent: mailSentAt !== null, telegramSent: telegramSentAt !== null, error };
}
