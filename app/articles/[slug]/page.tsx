import { ArticleLayout } from "@/components/ArticleLayout";
import { notFound } from "next/navigation";
import { getArticleBySlug, getAllArticles } from "@/lib/articles";
import { generateArticleJsonLd, generateBreadcrumbJsonLd } from "@/lib/seo";
import type { Metadata } from "next";
import Script from "next/script";

type Props = { params: Promise<{ slug: string }> };

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://faccel.jp";
const SITE_NAME = "ファクセル";
const DEFAULT_OG_IMAGE = "/images/hero-teleop.jpg";

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const article = await getArticleBySlug(slug);
  if (!article) return {};

  const url = `${SITE_URL}/articles/${slug}`;
  const title = `${article.title} | ${SITE_NAME}`;

  return {
    title: article.title,
    description: article.description,
    keywords: article.keywords,
    openGraph: {
      title,
      description: article.description,
      url,
      siteName: SITE_NAME,
      locale: "ja_JP",
      type: "article",
      publishedTime: article.date,
      authors: [article.author],
      images: [{ url: DEFAULT_OG_IMAGE, width: 1200, height: 630, alt: article.title }],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description: article.description,
      images: [DEFAULT_OG_IMAGE],
    },
    alternates: {
      canonical: url,
    },
  };
}

export function generateStaticParams() {
  const articles = getAllArticles();
  return articles.map((a) => ({ slug: a.slug }));
}

export default async function ArticlePage({ params }: Props) {
  const { slug } = await params;
  const article = await getArticleBySlug(slug);
  if (!article) notFound();

  const url = `${SITE_URL}/articles/${slug}`;

  const articleJsonLd = generateArticleJsonLd({
    slug,
    title: article.title,
    description: article.description,
    date: article.date,
    author: article.author,
    keywords: article.keywords,
    image: `${SITE_URL}${DEFAULT_OG_IMAGE}`,
  });

  const breadcrumbJsonLd = generateBreadcrumbJsonLd([
    { name: "ホーム", url: SITE_URL },
    { name: "コラム", url: `${SITE_URL}/articles` },
    { name: article.title, url },
  ]);

  return (
    <>
      <Script
        id="article-jsonld"
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(articleJsonLd) }}
      />
      <Script
        id="breadcrumb-jsonld"
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbJsonLd) }}
      />
      <ArticleLayout title={article.title} date={article.date} author={article.author}>
        <div dangerouslySetInnerHTML={{ __html: article.contentHtml }} />
      </ArticleLayout>
    </>
  );
}
