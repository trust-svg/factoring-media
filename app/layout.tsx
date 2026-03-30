import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "ファクタリング比較ナビ | 口コミ・評判で業者を徹底比較",
    template: "%s | ファクタリング比較ナビ",
  },
  description:
    "ファクタリング業者の口コミ・評判を比較。手数料・入金速度・審査の甘さで徹底比較。おすすめランキングや一括見積もりで最適な業者が見つかります。",
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000"
  ),
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
        <Header />
        <main className="flex-1">{children}</main>
        <Footer />
      </body>
    </html>
  );
}

function Header() {
  return (
    <header className="bg-navy text-white sticky top-0 z-50 shadow-md">
      <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
        <a href="/" className="text-xl font-bold tracking-tight">
          ファクタリング比較ナビ
        </a>
        <nav className="hidden md:flex items-center gap-6 text-sm font-medium">
          <a href="/companies" className="hover:text-green-light transition-colors">
            業者一覧
          </a>
          <a href="/ranking" className="hover:text-green-light transition-colors">
            ランキング
          </a>
          <a href="/reviews" className="hover:text-green-light transition-colors">
            口コミ
          </a>
          <a href="/articles" className="hover:text-green-light transition-colors">
            コラム
          </a>
          <a
            href="/estimate"
            className="bg-green hover:bg-green-dark text-white px-4 py-2 rounded-lg font-bold transition-colors"
          >
            無料一括見積もり
          </a>
        </nav>
        <button className="md:hidden text-white" aria-label="メニュー">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer className="bg-navy-dark text-gray-300 mt-16">
      <div className="max-w-6xl mx-auto px-4 py-12">
        <div className="grid md:grid-cols-4 gap-8">
          <div>
            <h3 className="text-white font-bold text-lg mb-4">ファクタリング比較ナビ</h3>
            <p className="text-sm leading-relaxed">
              ファクタリング業者の口コミ・評判を徹底比較。あなたに最適な業者選びをサポートします。
            </p>
          </div>
          <div>
            <h4 className="text-white font-bold mb-3">サービス</h4>
            <ul className="space-y-2 text-sm">
              <li><a href="/companies" className="hover:text-white transition-colors">業者一覧</a></li>
              <li><a href="/ranking" className="hover:text-white transition-colors">おすすめランキング</a></li>
              <li><a href="/reviews" className="hover:text-white transition-colors">口コミ一覧</a></li>
              <li><a href="/estimate" className="hover:text-white transition-colors">一括見積もり</a></li>
            </ul>
          </div>
          <div>
            <h4 className="text-white font-bold mb-3">お役立ち情報</h4>
            <ul className="space-y-2 text-sm">
              <li><a href="/articles" className="hover:text-white transition-colors">コラム・記事</a></li>
              <li><a href="/articles/what-is-factoring" className="hover:text-white transition-colors">ファクタリングとは</a></li>
              <li><a href="/articles/how-to-choose" className="hover:text-white transition-colors">業者の選び方</a></li>
            </ul>
          </div>
          <div>
            <h4 className="text-white font-bold mb-3">サイト情報</h4>
            <ul className="space-y-2 text-sm">
              <li><a href="/about" className="hover:text-white transition-colors">運営者情報</a></li>
              <li><a href="/privacy" className="hover:text-white transition-colors">プライバシーポリシー</a></li>
              <li><a href="/terms" className="hover:text-white transition-colors">利用規約</a></li>
            </ul>
          </div>
        </div>
        <div className="border-t border-gray-600 mt-8 pt-8 text-center text-sm">
          <p>&copy; 2026 ファクタリング比較ナビ All Rights Reserved.</p>
        </div>
      </div>
    </footer>
  );
}
