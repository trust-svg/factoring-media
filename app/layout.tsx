import type { Metadata } from "next";
import Image from "next/image";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "ファクセル | 口コミ・評判で業者を徹底比較【2026年最新】",
    template: "%s | ファクセル",
  },
  description:
    "ファクタリング業者の口コミ・評判を比較。手数料・入金速度・審査の甘さで徹底比較。おすすめランキングや一括見積もりで最適な業者が見つかります。",
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000"
  ),
  openGraph: {
    title: "ファクセル | 口コミ・評判で業者を徹底比較【2026年最新】",
    description: "ファクタリング業者10社の口コミ・手数料・入金速度を徹底比較。無料一括見積もりであなたに最適な業者が見つかります。",
    siteName: "ファクセル",
    locale: "ja_JP",
    type: "website",
    images: [
      {
        url: "/images/hero-teleop.jpg",
        width: 1200,
        height: 630,
        alt: "ファクセル",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "ファクセル | 口コミ・評判で業者を徹底比較",
    description: "ファクタリング業者10社の口コミ・手数料・入金速度を徹底比較。",
    images: ["/images/hero-teleop.jpg"],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700;900&display=swap"
          rel="stylesheet"
        />
        {process.env.NEXT_PUBLIC_GA_ID && (
          <>
            <script
              async
              src={`https://www.googletagmanager.com/gtag/js?id=${process.env.NEXT_PUBLIC_GA_ID}`}
            />
            <script
              dangerouslySetInnerHTML={{
                __html: `window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','${process.env.NEXT_PUBLIC_GA_ID}');`,
              }}
            />
          </>
        )}
      </head>
      <body className="min-h-screen flex flex-col">
        {/* Top bar - hidden, info moved to hero */}
        <div className="bg-primary-darker text-xs text-blue-200 py-1">
          <div className="max-w-6xl mx-auto px-4 flex justify-between items-center">
            <p>掲載業者数 <span className="text-white font-bold">10社</span> ｜ 口コミ掲載数 <span className="text-white font-bold">随時更新中</span></p>
            <p className="hidden sm:block">最終更新: 2026年3月</p>
          </div>
        </div>
        <Header />
        <main className="flex-1 pb-20 lg:pb-0">{children}</main>
        <CtaBanner />
        <Footer />
        <MobileFixedCta />
      </body>
    </html>
  );
}

function Header() {
  return (
    <header className="bg-white border-b border-gray-200 sticky top-0 z-50 shadow-sm">
      <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
        <a href="/" className="flex items-center gap-1">
          <Image src="/images/logo-faccel.png" alt="ファクセル" width={180} height={46} priority />
        </a>
        <nav className="hidden lg:flex items-center gap-1">
          <a href="/companies" className="px-3 py-2 text-sm font-medium text-gray-600 hover:text-primary hover:bg-primary/5 rounded-lg transition-all">
            業者一覧
          </a>
          <a href="/ranking" className="px-3 py-2 text-sm font-medium text-gray-600 hover:text-primary hover:bg-primary/5 rounded-lg transition-all">
            ランキング
          </a>
          <a href="/reviews" className="px-3 py-2 text-sm font-medium text-gray-600 hover:text-primary hover:bg-primary/5 rounded-lg transition-all">
            口コミ
          </a>
          <a href="/articles" className="px-3 py-2 text-sm font-medium text-gray-600 hover:text-primary hover:bg-primary/5 rounded-lg transition-all">
            コラム
          </a>
          <a
            href="/estimate"
            className="ml-2 bg-cta hover:bg-cta-dark text-white px-5 py-2.5 rounded-lg font-bold transition-colors text-sm shadow-md pulse-cta"
          >
            無料一括見積もり
          </a>
        </nav>
        <button className="lg:hidden text-gray-600" aria-label="メニュー">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
      </div>
    </header>
  );
}

function CtaBanner() {
  return (
    <div className="bg-gradient-to-r from-primary to-secondary py-10">
      <div className="max-w-3xl mx-auto px-4 text-center text-white">
        <p className="text-sm font-medium mb-2 text-blue-100">最適なファクタリング業者をお探しの方</p>
        <h2 className="text-xl md:text-2xl font-bold mb-4">
          30秒の入力で複数社の見積もりを無料比較
        </h2>
        <a
          href="/estimate"
          className="inline-block bg-cta hover:bg-cta-dark text-white px-10 py-4 rounded-xl text-lg font-bold transition-colors shadow-lg pulse-cta"
        >
          無料で一括見積もりする
        </a>
        <p className="text-xs text-blue-200 mt-3">※ 利用料は一切かかりません</p>
      </div>
    </div>
  );
}

function MobileFixedCta() {
  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 lg:hidden bg-white border-t border-gray-200 shadow-[0_-4px_20px_rgba(0,0,0,0.1)] px-4 py-3">
      <a
        href="/estimate"
        className="block w-full bg-cta hover:bg-cta-dark text-white text-center py-3 rounded-xl font-bold text-sm shadow-md pulse-cta"
      >
        無料で一括見積もり（30秒で完了）
      </a>
    </div>
  );
}

function Footer() {
  return (
    <footer className="bg-gray-900 text-gray-400">
      <div className="max-w-6xl mx-auto px-4 py-12">
        <div className="grid md:grid-cols-4 gap-8">
          <div>
            <div className="mb-4">
              <span className="text-white font-bold text-lg">ファクセル</span>
            </div>
            <p className="text-sm leading-relaxed">
              ファクタリング業者の口コミ・評判を徹底比較。あなたに最適な業者選びをサポートします。
            </p>
          </div>
          <div>
            <h4 className="text-white font-bold mb-3 text-sm">サービス</h4>
            <ul className="space-y-2 text-sm">
              <li><a href="/companies" className="hover:text-white transition-colors">業者一覧</a></li>
              <li><a href="/ranking" className="hover:text-white transition-colors">おすすめランキング</a></li>
              <li><a href="/reviews" className="hover:text-white transition-colors">口コミ一覧</a></li>
              <li><a href="/estimate" className="hover:text-white transition-colors">一括見積もり</a></li>
            </ul>
          </div>
          <div>
            <h4 className="text-white font-bold mb-3 text-sm">お役立ち情報</h4>
            <ul className="space-y-2 text-sm">
              <li><a href="/articles" className="hover:text-white transition-colors">コラム・記事</a></li>
              <li><a href="/articles/what-is-factoring" className="hover:text-white transition-colors">ファクタリングとは</a></li>
              <li><a href="/articles/how-to-choose" className="hover:text-white transition-colors">業者の選び方</a></li>
              <li><a href="/articles/factoring-illegal" className="hover:text-white transition-colors">違法業者の見分け方</a></li>
            </ul>
          </div>
          <div>
            <h4 className="text-white font-bold mb-3 text-sm">サイト情報</h4>
            <ul className="space-y-2 text-sm">
              <li><a href="/about" className="hover:text-white transition-colors">運営者情報</a></li>
              <li><a href="/privacy" className="hover:text-white transition-colors">プライバシーポリシー</a></li>
              <li><a href="/terms" className="hover:text-white transition-colors">利用規約</a></li>
            </ul>
          </div>
        </div>
        <div className="border-t border-gray-800 mt-8 pt-8 text-center text-xs">
          <p>&copy; 2026 ファクセル All Rights Reserved.</p>
          <p className="mt-1 text-gray-500">※ 当サイトはアフィリエイトプログラムに参加しています。</p>
        </div>
      </div>
    </footer>
  );
}
