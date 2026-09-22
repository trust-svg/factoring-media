import { NextResponse, type NextRequest } from "next/server";
import { extractAuctionId, fetchAuctionInfo, judgeSeller } from "@yar/shared";
import { requireUser } from "@/lib/auth";
import { handle, jsonError } from "@/lib/api";

// 予約登録前の商品情報プレビュー(設計 §9, §10)
export async function POST(req: NextRequest) {
  return handle(async () => {
    const user = await requireUser();
    const { url } = await req.json();
    if (typeof url !== "string" || !extractAuctionId(url)) {
      return jsonError(400, "ヤフオクの商品URLを入力してください");
    }
    try {
      const info = await fetchAuctionInfo(url);
      // 足切り判定は確認画面で見せる。POST まで黙っていると、
      // 「登録ボタンを押したら断られた」という体験になる。
      const seller = judgeSeller(
        {
          sellerRating: info.sellerRating ?? null,
          sellerRatingCount: info.sellerRatingCount ?? null,
        },
        {
          sellerRatingFloor: user.sellerRatingFloor,
          sellerRatingMinCount: user.sellerRatingMinCount,
        },
      );
      return NextResponse.json({
        ...info,
        sellerJudgement: seller,
        sellerBlocks: seller.level === "warn" && user.blockLowRatedSeller,
      });
    } catch {
      return jsonError(502, "商品情報の取得に失敗しました。URLをご確認ください");
    }
  });
}
