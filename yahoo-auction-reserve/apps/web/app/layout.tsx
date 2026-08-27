import type { Metadata, Viewport } from "next";
import Link from "next/link";
import "./globals.css";
import { prisma } from "@yar/db";
import { canRegister } from "@yar/shared";
import { getSessionUser } from "@/lib/auth";
import LogoutButton from "./LogoutButton";
import { SideNav, TabBar } from "./AppNav";
import WorkerAlert from "./WorkerAlert";

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

  // 未ログイン時に「新規登録」を出すかどうか。
  //
  // ⚠️ 登録は「利用者が0人のときだけ」自動的に開く(packages/shared/src/access.ts)。
  //    ここを常に出していたため、URL を開くと登録画面へ誘導されるのに
  //    登録は断られるという行き止まりができていた。判定は API 側と
  //    **同じ関数** を使う。文言や条件を書き写すと必ずズレる。
  const registrationOpen =
    user === null &&
    canRegister({
      allowFlag: process.env.ALLOW_REGISTRATION,
      existingUserCount: await prisma.user.count(),
    }).allowed;

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
              <main>
                <WorkerAlert />
                {children}
              </main>
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
                  {registrationOpen && <Link href="/register">新規登録</Link>}
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
