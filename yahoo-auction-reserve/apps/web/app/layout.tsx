import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { getSessionUser } from "@/lib/auth";

export const metadata: Metadata = {
  title: "ヤフオク入札予約",
  description: "オークション終了直前に自動入札(スナイプ入札)を実行する予約サービス",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await getSessionUser();
  return (
    <html lang="ja">
      <body>
        <header className="header">
          <Link href="/">
            <strong>ヤフオク入札予約</strong>
          </Link>
          <nav>
            {user ? (
              <>
                <Link href="/dashboard">予約一覧</Link>
                <Link href="/reservations/new">新規予約</Link>
                <Link href="/settings/yahoo">ヤフオク連携</Link>
                <span className="muted">{user.email}</span>
              </>
            ) : (
              <>
                <Link href="/login">ログイン</Link>
                <Link href="/register">新規登録</Link>
              </>
            )}
          </nav>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
