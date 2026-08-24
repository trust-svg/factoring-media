import Link from "next/link";
import { redirect } from "next/navigation";
import { prisma } from "@yar/db";
import { SESSION_STATUS_LABEL } from "@yar/shared/labels";
import { getSessionUser } from "@/lib/auth";
import LogoutButton from "../LogoutButton";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const user = await getSessionUser();
  if (!user) redirect("/login");

  const [sessions, notify] = await Promise.all([
    prisma.yahooSession.findMany({ where: { userId: user.id } }),
    prisma.notificationSetting.findUnique({ where: { userId: user.id } }),
  ]);
  const active = sessions.filter((s) => s.status === "ACTIVE");

  return (
    <>
      <h1>設定</h1>
      <div className="card">
        <h2>
          <Link href="/settings/yahoo">ヤフオク連携</Link>
        </h2>
        {sessions.length === 0 ? (
          <p className="error">未連携です。連携しないと入札は実行されません。</p>
        ) : (
          <p className="muted">
            {sessions.length}件登録 / 有効 {active.length}件
            {sessions.length > active.length && (
              <>
                {" — "}
                <span className="error">
                  {sessions
                    .filter((s) => s.status !== "ACTIVE")
                    .map((s) => `${s.label}: ${SESSION_STATUS_LABEL[s.status]}`)
                    .join(" / ")}
                </span>
              </>
            )}
          </p>
        )}
      </div>

      <div className="card">
        <h2>
          <Link href="/settings/notifications">通知</Link>
        </h2>
        <p className="muted">
          {notify?.telegramChatId ? "Telegram 連携済み" : "Telegram 未連携(メールのみ)"} /{" "}
          リマインド{" "}
          {notify && notify.remindMinutesBefore.length > 0
            ? notify.remindMinutesBefore.map((m) => `${m}分前`).join(" · ")
            : "なし"}{" "}
          / 稼働サマリ {notify?.dailySummaryAt ?? "なし"}
        </p>
      </div>

      <div className="card">
        <h2>アカウント</h2>
        <p className="muted">{user.email}</p>
        <LogoutButton />
      </div>
    </>
  );
}
