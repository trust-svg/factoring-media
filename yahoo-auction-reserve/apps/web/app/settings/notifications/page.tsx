import Link from "next/link";
import { redirect } from "next/navigation";
import { prisma } from "@yar/db";
import { getSessionUser } from "@/lib/auth";
import NotificationForm from "./NotificationForm";

export const dynamic = "force-dynamic";

export default async function NotificationSettingsPage() {
  const user = await getSessionUser();
  if (!user) redirect("/login");

  const setting = await prisma.notificationSetting.findUnique({
    where: { userId: user.id },
  });

  return (
    <>
      <div className="page-head">
        <h1>通知</h1>
        <Link href="/settings">設定に戻る</Link>
      </div>
      <div className="card">
        <NotificationForm
          // トークンの有無だけを渡す。値そのものはクライアントへ出さない(設計 §8)。
          telegramConfigured={Boolean(process.env.TELEGRAM_BOT_TOKEN)}
          initial={{
            telegramChatId: setting?.telegramChatId ?? "",
            remindMinutesBefore: setting?.remindMinutesBefore ?? [],
            notifyResult: setting?.notifyResult ?? true,
            notifyError: setting?.notifyError ?? true,
            dailySummaryAt: setting?.dailySummaryAt ?? "",
          }}
        />
      </div>
    </>
  );
}
