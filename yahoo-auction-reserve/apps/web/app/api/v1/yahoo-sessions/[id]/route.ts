import { NextResponse } from "next/server";
import { prisma } from "@yar/db";
import { planSessionRemoval } from "@yar/shared";
import { requireUser } from "@/lib/auth";
import { handle, jsonError } from "@/lib/api";

// 連携解除。
//
// ⚠️ 設計 §8 は「物理削除」だったが、予約とウォッチの外部キーは RESTRICT
//    なので **一度でも使った連携は DB が削除を拒否する**。2026-09-22 まで、
//    そこを見ずに delete を呼んでいたため P2003 で 500 になり、画面には
//    「サーバーエラーが発生しました」しか出ず、消えない理由が分からなかった。
//    使った連携は無害化(Cookie を捨てて REVOKED)にする。判定は
//    shared/sessionRemoval.ts。
export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  return handle(async () => {
    const user = await requireUser();
    const { id } = await params;
    const session = await prisma.yahooSession.findUnique({ where: { id } });
    if (!session || session.userId !== user.id) {
      return jsonError(404, "連携が見つかりません");
    }
    const active = await prisma.bidReservation.count({
      where: {
        yahooSessionId: id,
        status: { in: ["SCHEDULED", "MONITORING", "BIDDING"] },
      },
    });
    if (active > 0) {
      return jsonError(409, "この連携を使う実行前の予約があります。先に予約をキャンセルしてください");
    }

    const [reservations, watchlistItems] = await Promise.all([
      prisma.bidReservation.count({ where: { yahooSessionId: id } }),
      prisma.watchlistItem.count({ where: { yahooSessionId: id } }),
    ]);
    const plan = planSessionRemoval({ reservations, watchlistItems });

    if (plan.mode === "delete") {
      await prisma.yahooSession.delete({ where: { id } });
      return NextResponse.json({ ok: true, mode: "delete" });
    }

    // Cookie は捨てる。解除の主目的は認証情報を残さないことで、それは
    // 行を消さなくても果たせる。復号できる値を空文字にしておくと、
    // 万一 ACTIVE に戻されても注入する Cookie が無く実行できない。
    await prisma.yahooSession.update({
      where: { id },
      data: {
        encryptedCookie: "",
        status: "REVOKED",
        watchlistSyncRequestedAt: null,
      },
    });
    return NextResponse.json({ ok: true, mode: "revoke", message: plan.reason });
  });
}
