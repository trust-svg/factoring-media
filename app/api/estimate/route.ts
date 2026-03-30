import { prisma } from "@/lib/prisma";
import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { businessType, invoiceAmount, urgency, email, phone, memo } = body;

    if (!businessType || !invoiceAmount || !urgency || !email) {
      return NextResponse.json(
        { error: "必須項目を入力してください" },
        { status: 400 }
      );
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      return NextResponse.json(
        { error: "有効なメールアドレスを入力してください" },
        { status: 400 }
      );
    }

    const estimate = await prisma.estimateRequest.create({
      data: {
        businessType,
        invoiceAmount: parseInt(invoiceAmount),
        urgency,
        email: email.trim(),
        phone: phone?.trim() || null,
        memo: memo?.trim() || null,
      },
    });

    return NextResponse.json({ success: true, id: estimate.id });
  } catch {
    return NextResponse.json(
      { error: "サーバーエラーが発生しました" },
      { status: 500 }
    );
  }
}
