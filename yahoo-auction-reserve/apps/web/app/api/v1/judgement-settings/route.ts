import { NextResponse, type NextRequest } from "next/server";
import { prisma } from "@yar/db";
import { requireUser } from "@/lib/auth";
import { handle, jsonError } from "@/lib/api";

// 出品者の足切りしきい値(設計追補 2026-08-25)。
// 既定は「判定しない(null)」。推測でしきい値を入れると、ユーザーからは
// 「なぜか予約できない商品がある」という形でしか見えない。
const RATING_MIN = 0;
const RATING_MAX = 100;
const COUNT_MAX = 1_000_000;

/** 空文字・null・undefined を「未設定」に寄せる。0 は有効な値なので落とさない。 */
function optionalInt(value: unknown): number | null | undefined {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  if (!Number.isInteger(n)) return undefined; // 不正値
  return n;
}

export async function GET() {
  return handle(async () => {
    const user = await requireUser();
    return NextResponse.json({
      sellerRatingFloor: user.sellerRatingFloor,
      sellerRatingMinCount: user.sellerRatingMinCount,
      blockLowRatedSeller: user.blockLowRatedSeller,
    });
  });
}

export async function PUT(req: NextRequest) {
  return handle(async () => {
    const user = await requireUser();
    const body = await req.json();

    const floor = optionalInt(body.sellerRatingFloor);
    if (floor === undefined || (floor !== null && (floor < RATING_MIN || floor > RATING_MAX))) {
      return jsonError(400, `評価の下限は${RATING_MIN}〜${RATING_MAX}(%)の整数で指定してください`);
    }
    const minCount = optionalInt(body.sellerRatingMinCount);
    if (minCount === undefined || (minCount !== null && (minCount < 0 || minCount > COUNT_MAX))) {
      return jsonError(400, "評価件数の下限は0以上の整数で指定してください");
    }

    const blockLowRatedSeller = body.blockLowRatedSeller === true;
    // しきい値が1つも無いのに「登録をブロック」だけ ON にすると、判定が
    // 常に ok になって永久に何も起きない。設定画面で気づけないので断る。
    if (blockLowRatedSeller && floor === null && minCount === null) {
      return jsonError(
        400,
        "ブロックを有効にするには、評価の下限か評価件数の下限を少なくとも1つ設定してください",
      );
    }

    const saved = await prisma.user.update({
      where: { id: user.id },
      data: {
        sellerRatingFloor: floor,
        sellerRatingMinCount: minCount,
        blockLowRatedSeller,
      },
      select: {
        sellerRatingFloor: true,
        sellerRatingMinCount: true,
        blockLowRatedSeller: true,
      },
    });
    return NextResponse.json(saved);
  });
}
