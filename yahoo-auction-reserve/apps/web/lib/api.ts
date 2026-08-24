import { NextResponse } from "next/server";
import { UnauthorizedError } from "./auth";

export function jsonError(status: number, message: string): NextResponse {
  return NextResponse.json({ error: message }, { status });
}

// Route Handler 共通のエラーハンドリング
export async function handle<T>(
  fn: () => Promise<T>,
): Promise<NextResponse | T> {
  try {
    return await fn();
  } catch (err) {
    if (err instanceof UnauthorizedError) return jsonError(401, "ログインが必要です");
    console.error("[api]", err);
    return jsonError(500, "サーバーエラーが発生しました");
  }
}
