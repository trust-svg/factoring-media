import { NextResponse, type NextRequest } from "next/server";
import { extractAuctionId, fetchAuctionInfo } from "@yar/shared";
import { requireUser } from "@/lib/auth";
import { handle, jsonError } from "@/lib/api";

// 予約登録前の商品情報プレビュー(設計 §9, §10)
export async function POST(req: NextRequest) {
  return handle(async () => {
    await requireUser();
    const { url } = await req.json();
    if (typeof url !== "string" || !extractAuctionId(url)) {
      return jsonError(400, "ヤフオクの商品URLを入力してください");
    }
    try {
      const info = await fetchAuctionInfo(url);
      return NextResponse.json(info);
    } catch {
      return jsonError(502, "商品情報の取得に失敗しました。URLをご確認ください");
    }
  });
}
