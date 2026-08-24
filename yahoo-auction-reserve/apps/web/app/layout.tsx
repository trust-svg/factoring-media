import type { Metadata, Viewport } from "next";
import Link from "next/link";
import "./globals.css";
import { getSessionUser } from "@/lib/auth";
import LogoutButton from "./LogoutButton";
import { SideNav, TabBar } from "./AppNav";

export const metadata: Metadata = {
  title: "ヤフオク入札予約",
  description: "オークション終了直前に自動入札(スナイプ入札)を実行する予約サービス",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, title: "入札予約", statusBarStyle: "default" },
};

// viewportFit: "cover" が無いと、iOS のホーム画面から起動したときに
// 下タブがホームインジケータに潜り込む(env(safe-area-inset-*) も 0 になる)。
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#eceff2" },
    { media: "(prefers-color-scheme: dark)", color: "#0f1317" },
  ],
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await getSessionUser();
  return (
    <html lang="ja">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600&family=IBM+Plex+Sans+JP:wght@400;500;600&display=swap"
        />
      </head>
      <body>
        <div className="app">
          {user ? (
            <>
              <SideNav email={user.email} />
              <header className="topbar">
                <Link href="/dashboard" className="brand">
                  ヤフオク入札予約
                </Link>
                <LogoutButton />
              </header>
              <main>{children}</main>
              <TabBar />
            </>
          ) : (
            <>
              <header className="topbar">
                <Link href="/" className="brand">
                  ヤフオク入札予約
                </Link>
                <nav className="row">
                  <Link href="/login">ログイン</Link>
                  <Link href="/register">新規登録</Link>
                </nav>
              </header>
              <main>{children}</main>
            </>
          )}
        </div>
      </body>
    </html>
  );
}
