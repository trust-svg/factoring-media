import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "ファクタリングお役立ちコラム",
  description:
    "ファクタリングに関する基礎知識、業者の選び方、注意点などをわかりやすく解説するコラム記事一覧。",
};

const articles = [
  {
    slug: "what-is-factoring",
    title: "ファクタリングとは？仕組み・種類・メリットをわかりやすく解説",
    excerpt:
      "ファクタリングの基本的な仕組み、2社間・3社間の違い、メリット・デメリットを初心者向けにわかりやすく解説します。",
    date: "2026-03-01",
    category: "基礎知識",
  },
  {
    slug: "how-to-choose",
    title: "失敗しないファクタリング業者の選び方【7つのチェックポイント】",
    excerpt:
      "手数料だけで選ぶと失敗する？信頼できるファクタリング業者を見極めるための7つのチェックポイントを解説。",
    date: "2026-03-05",
    category: "業者選び",
  },
  {
    slug: "fee-comparison",
    title: "ファクタリング手数料の相場は？業者別に徹底比較【2026年版】",
    excerpt:
      "2社間・3社間のファクタリング手数料の相場と、主要10社の手数料を一覧で比較します。",
    date: "2026-03-10",
    category: "費用",
  },
  {
    slug: "vs-bank-loan",
    title: "ファクタリングと銀行融資の違い｜どちらを選ぶべき？",
    excerpt:
      "ファクタリングと銀行融資の違いを「スピード」「審査基準」「コスト」の3軸で比較し、適切な選択をサポート。",
    date: "2026-03-15",
    category: "比較",
  },
  {
    slug: "illegal-factoring",
    title: "悪徳ファクタリング業者の見分け方と被害事例",
    excerpt:
      "違法な給与ファクタリングや闇金まがいの業者を見抜くポイントと、実際の被害事例を紹介します。",
    date: "2026-03-20",
    category: "注意点",
  },
];

export default function ArticlesPage() {
  return (
    <div className="max-w-4xl mx-auto px-4 py-10">
      <h1 className="text-2xl md:text-3xl font-bold text-navy mb-2">
        お役立ちコラム
      </h1>
      <p className="text-gray-500 mb-8">
        ファクタリングに関する基礎知識から業者の選び方まで、お役立ち情報を掲載しています
      </p>

      <div className="space-y-6">
        {articles.map((article) => (
          <Link
            key={article.slug}
            href={`/articles/${article.slug}`}
            className="block bg-white border border-gray-200 rounded-xl p-6 hover:shadow-md hover:border-navy/20 transition-all"
          >
            <div className="flex items-center gap-3 mb-2">
              <span className="text-xs bg-navy/10 text-navy px-2.5 py-1 rounded-full font-medium">
                {article.category}
              </span>
              <time className="text-xs text-gray-400">{article.date}</time>
            </div>
            <h2 className="text-lg font-bold text-navy mb-2">{article.title}</h2>
            <p className="text-sm text-gray-600">{article.excerpt}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
