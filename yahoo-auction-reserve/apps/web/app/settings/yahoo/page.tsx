import { redirect } from "next/navigation";
import { prisma } from "@yar/db";
import { getSessionUser } from "@/lib/auth";
import YahooSessionManager from "./YahooSessionManager";

export const dynamic = "force-dynamic";

export default async function YahooSettingsPage() {
  const user = await getSessionUser();
  if (!user) redirect("/login");

  // Cookie本体(encryptedCookie)は決してクライアントへ渡さない(設計 §8)
  const sessions = await prisma.yahooSession.findMany({
    where: { userId: user.id },
    select: {
      id: true,
      label: true,
      status: true,
      lastVerifiedAt: true,
      createdAt: true,
    },
    orderBy: { createdAt: "desc" },
  });

  const activeCounts = await prisma.bidReservation.groupBy({
    by: ["yahooSessionId"],
    where: {
      userId: user.id,
      status: { in: ["SCHEDULED", "MONITORING", "BIDDING"] },
    },
    _count: { _all: true },
  });
  const activeBySession = Object.fromEntries(
    activeCounts.map((c) => [c.yahooSessionId, c._count._all]),
  );

  return (
    <YahooSessionManager
      sessions={sessions.map((s) => ({
        id: s.id,
        label: s.label,
        status: s.status,
        lastVerifiedAt: s.lastVerifiedAt?.toISOString() ?? null,
        createdAt: s.createdAt.toISOString(),
        activeReservations: activeBySession[s.id] ?? 0,
      }))}
    />
  );
}
