import type { Metadata } from "next";
import Link from "next/link";
import { getAllArticles } from "@/lib/articles";

export const metadata: Metadata = {
  title: "ファクタリングお役立ちコラム",
  description:
    "ファクタリングに関する基礎知識、業者の選び方、注意点などをわかりやすく解説するコラム記事一覧。",
};

export default function ArticlesPage() {
  const articles = getAllArticles();

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
            <p className="text-sm text-gray-600">{article.description}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
