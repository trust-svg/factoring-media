import { prisma } from "@/lib/prisma";
import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { companyId, rating, title, body: reviewBody, userType } = body;

    if (!companyId || !rating || !title || !reviewBody) {
      return NextResponse.json(
        { error: "必須項目を入力してください" },
        { status: 400 }
      );
    }

    if (rating < 1 || rating > 5) {
      return NextResponse.json(
        { error: "評価は1〜5の範囲で入力してください" },
        { status: 400 }
      );
    }

    if (title.length > 100) {
      return NextResponse.json(
        { error: "タイトルは100文字以内で入力してください" },
        { status: 400 }
      );
    }

    if (reviewBody.length > 2000) {
      return NextResponse.json(
        { error: "口コミ内容は2000文字以内で入力してください" },
        { status: 400 }
      );
    }

    const review = await prisma.review.create({
      data: {
        companyId: parseInt(companyId),
        rating: parseInt(rating),
        title: title.trim(),
        body: reviewBody.trim(),
        userType: userType || null,
        isApproved: false,
      },
    });

    return NextResponse.json({ success: true, id: review.id });
  } catch {
    return NextResponse.json(
      { error: "サーバーエラーが発生しました" },
      { status: 500 }
    );
  }
}
