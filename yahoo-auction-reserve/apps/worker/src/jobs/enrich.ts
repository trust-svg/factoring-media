import { prisma } from "@yar/db";
import { fetchMarketStats } from "@yar/shared";

// 1走査で調べる件数。落札相場ページを叩くので少しずつ流す。
const ENRICH_BATCH = 5;

/**
 * 判断材料(落札相場)の後追い取得。
 *
 * 予約登録時に相場まで取ると登録が遅くなり、相場ページ側の不調で登録自体が
 * 失敗する。登録は通してから、ここで埋める。
 *
 * ⚠️ 失敗しても marketCheckedAt は必ず進める。進めないと同じ1件を毎走査
 * 叩き続け、後ろの予約が永久に順番待ちになる(=「相場が出ない予約がある」と
 * いう形でしか表面化しない)。失敗は marketSampleCount = null で区別する。
 */
export async function runEnrichSweep(): Promise<void> {
  const targets = await prisma.bidReservation.findMany({
    where: { status: "SCHEDULED", marketCheckedAt: null },
    select: { id: true, title: true },
    orderBy: { createdAt: "asc" },
    take: ENRICH_BATCH,
  });

  for (const r of targets) {
    try {
      const stats = await fetchMarketStats(r.title);
      await prisma.bidReservation.update({
        where: { id: r.id },
        data: {
          marketMedianPrice: stats.medianPrice,
          marketSampleCount: stats.sampleCount,
          marketCheckedAt: new Date(),
        },
      });
      console.log(
        `[enrich] ${r.id}: 中央値=${stats.medianPrice ?? "該当なし"} 母数=${stats.sampleCount} 検索語="${stats.query}"`,
      );
    } catch (err) {
      await prisma.bidReservation
        .update({
          where: { id: r.id },
          data: { marketCheckedAt: new Date(), marketSampleCount: null },
        })
        .catch(() => {});
      console.error(`[enrich] ${r.id} の相場取得に失敗:`, err);
    }
  }
}
