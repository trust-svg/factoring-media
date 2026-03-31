type ArticleLayoutProps = {
  title: string;
  date?: string;
  author?: string;
  children: React.ReactNode;
};

export function ArticleLayout({ title, date, author, children }: ArticleLayoutProps) {
  return (
    <article className="max-w-3xl mx-auto px-4 py-8">
      <header className="mb-8">
        <h1 className="text-2xl md:text-3xl font-bold text-navy leading-tight mb-4">
          {title}
        </h1>
        <div className="flex items-center gap-4 text-sm text-gray-500">
          {date && <time>{date}</time>}
          {author && <span>著者: {author}</span>}
        </div>
      </header>
      <div className="prose prose-navy max-w-none [&_h2]:text-xl [&_h2]:font-bold [&_h2]:text-navy [&_h2]:mt-10 [&_h2]:mb-4 [&_h2]:pb-2 [&_h2]:border-b [&_h2]:border-gray-200 [&_h3]:text-lg [&_h3]:font-bold [&_h3]:text-navy [&_h3]:mt-8 [&_h3]:mb-3 [&_p]:text-gray-700 [&_p]:leading-relaxed [&_p]:mb-4 [&_ul]:space-y-2 [&_ul]:mb-4 [&_li]:text-gray-700 [&_a]:text-navy [&_a]:underline [&_a]:hover:text-green">
        {children}
      </div>
      <div className="mt-12 bg-green/10 border border-green rounded-xl p-6 text-center">
        <p className="text-lg font-bold text-navy mb-2">
          最適なファクタリング業者をお探しですか？
        </p>
        <p className="text-sm text-gray-600 mb-4">
          無料で複数社の業者を比較できます
        </p>
        <a
          href="/estimate"
          className="inline-block bg-green text-white px-8 py-3 rounded-lg font-bold hover:bg-green-dark transition-colors"
        >
          無料で診断する
        </a>
      </div>
    </article>
  );
}
