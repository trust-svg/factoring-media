import Link from "next/link";
import { redirect } from "next/navigation";
import { prisma } from "@yar/db";
import {
  SNIPE_SECONDS_DEFAULT,
  SNIPE_SECONDS_MAX,
  SNIPE_SECONDS_MIN,
} from "@yar/shared";
import { getSessionUser } from "@/lib/auth";
import NewReservationForm from "./NewReservationForm";

export const dynamic = "force-dynamic";

export default async function NewReservationPage() {
  const user = await getSessionUser();
  if (!user) redirect("/login");

  const sessions = await prisma.yahooSession.findMany({
    where: { userId: user.id, status: "ACTIVE" },
    select: { id: true, label: true },
    orderBy: { createdAt: "desc" },
  });

  if (sessions.length === 0) {
    return (
      <div className="card">
        <h2>先にヤフオク連携が必要です</h2>
        <p>
          入札はご本人のヤフオクアカウントで実行します。
          <Link href="/settings/yahoo">ヤフオク連携</Link>
          からログイン済み Cookie を登録してください。
        </p>
      </div>
    );
  }

  return (
    <NewReservationForm
      sessions={sessions}
      snipeDefaults={{
        default: SNIPE_SECONDS_DEFAULT,
        min: SNIPE_SECONDS_MIN,
        max: SNIPE_SECONDS_MAX,
      }}
    />
  );
}
