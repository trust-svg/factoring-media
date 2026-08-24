import nodemailer from "nodemailer";
import { Prisma, prisma } from "@yar/db";
import type { NotificationType } from "@yar/shared";

const transporter = process.env.SMTP_HOST
  ? nodemailer.createTransport({
      host: process.env.SMTP_HOST,
      port: Number(process.env.SMTP_PORT ?? 587),
      auth: process.env.SMTP_USER
        ? { user: process.env.SMTP_USER, pass: process.env.SMTP_PASS }
        : undefined,
    })
  : null;

const SUBJECTS: Record<NotificationType, string> = {
  WON: "【落札成功】入札予約が落札されました",
  LOST: "【落札ならず】高値更新されました",
  FAILED: "【要確認】入札の実行に失敗しました",
  EXPIRED: "【スキップ】現在価格が上限額を超えました",
  SESSION_EXPIRED: "【要対応】ヤフオク連携が切れています",
};

export async function notifyUser(
  userId: string,
  type: NotificationType,
  payload: Record<string, unknown>,
): Promise<void> {
  const notification = await prisma.notification.create({
    data: { userId, type, payload: payload as Prisma.InputJsonObject },
  });

  const user = await prisma.user.findUnique({ where: { id: userId } });
  if (!user) return;

  const subject = SUBJECTS[type];
  const body = [
    subject,
    "",
    ...Object.entries(payload).map(([k, v]) => `${k}: ${String(v)}`),
  ].join("\n");

  if (transporter) {
    try {
      await transporter.sendMail({
        from: process.env.MAIL_FROM ?? "no-reply@localhost",
        to: user.email,
        subject,
        text: body,
      });
      await prisma.notification.update({
        where: { id: notification.id },
        data: { sentAt: new Date() },
      });
    } catch (err) {
      console.error(`[notify] mail send failed for ${userId}:`, err);
    }
  } else {
    console.log(`[notify] (mail disabled) to=${user.email}\n${body}`);
  }
}
