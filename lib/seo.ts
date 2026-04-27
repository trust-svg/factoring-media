import type { Metadata } from "next";

const SITE_NAME = "ファクセル";
const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://faccel.jp";
const DEFAULT_DESCRIPTION =
  "ファクタリング業者の口コミ・評判を比較。手数料・入金速度・審査の甘さで徹底比較。おすすめランキングや無料診断で最適な業者が見つかります。";

export function generateMetadata({
  title,
  description,
  path = "",
  noIndex = false,
}: {
  title: string;
  description?: string;
  path?: string;
  noIndex?: boolean;
}): Metadata {
  const fullTitle = `${title} | ${SITE_NAME}`;
  const desc = description || DEFAULT_DESCRIPTION;
  const url = `${SITE_URL}${path}`;

  return {
    title: fullTitle,
    description: desc,
    openGraph: {
      title: fullTitle,
      description: desc,
      url,
      siteName: SITE_NAME,
      locale: "ja_JP",
      type: "website",
    },
    twitter: {
      card: "summary_large_image",
      title: fullTitle,
      description: desc,
    },
    alternates: {
      canonical: url,
    },
    ...(noIndex && { robots: { index: false, follow: false } }),
  };
}

export function generateCompanyJsonLd(company: {
  name: string;
  description: string;
  officialUrl: string;
  rating?: number | null;
  reviewCount: number;
  slug: string;
}) {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: company.name,
    description: company.description,
    url: company.officialUrl,
    ...(company.rating && {
      aggregateRating: {
        "@type": "AggregateRating",
        ratingValue: company.rating,
        bestRating: 5,
        worstRating: 1,
        reviewCount: company.reviewCount || 1,
      },
    }),
  };
}

type AuthorEntry =
  | { type: "person"; name: string; url?: string; jobTitle?: string; sameAs?: string[]; description?: string; knowsAbout?: string[] }
  | { type: "organization"; name: string; url?: string };

const FACCEL_AUTHORS: Record<string, AuthorEntry> = {
  "ファクセル編集部": {
    type: "organization",
    name: "ファクセル編集部",
    url: `${SITE_URL}/about`,
  },
};

function buildAuthorJsonLd(authorName: string) {
  const meta = FACCEL_AUTHORS[authorName];
  if (!meta) {
    return { "@type": "Organization", name: authorName };
  }
  if (meta.type === "organization") {
    return {
      "@type": "Organization",
      name: meta.name,
      ...(meta.url && { url: meta.url }),
    };
  }
  return {
    "@type": "Person",
    name: meta.name,
    ...(meta.url && { url: meta.url }),
    ...(meta.jobTitle && { jobTitle: meta.jobTitle }),
    ...(meta.description && { description: meta.description }),
    ...(meta.sameAs?.length && { sameAs: meta.sameAs }),
    ...(meta.knowsAbout?.length && { knowsAbout: meta.knowsAbout }),
    worksFor: {
      "@type": "Organization",
      name: SITE_NAME,
      url: SITE_URL,
    },
  };
}

export function generateArticleJsonLd(article: {
  slug: string;
  title: string;
  description: string;
  date: string;
  modified?: string;
  author: string;
  keywords?: string[];
  image?: string;
}) {
  const url = `${SITE_URL}/articles/${article.slug}`;
  const image = article.image || `${SITE_URL}/images/hero-teleop.jpg`;
  return {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: article.title,
    description: article.description,
    image,
    datePublished: article.date,
    dateModified: article.modified || article.date,
    author: buildAuthorJsonLd(article.author),
    publisher: {
      "@type": "Organization",
      name: SITE_NAME,
      url: SITE_URL,
      logo: {
        "@type": "ImageObject",
        url: `${SITE_URL}/images/logo.png`,
      },
    },
    url,
    mainEntityOfPage: { "@type": "WebPage", "@id": url },
    ...(article.keywords?.length && { keywords: article.keywords.join(", ") }),
  };
}

export function generateBreadcrumbJsonLd(items: Array<{ name: string; url?: string }>) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: item.name,
      ...(item.url && { item: item.url }),
    })),
  };
}

export function generateFAQPageJsonLd(faqs: Array<{ question: string; answer: string }>) {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faqs.map((f) => ({
      "@type": "Question",
      name: f.question,
      acceptedAnswer: {
        "@type": "Answer",
        text: f.answer,
      },
    })),
  };
}

export function generateHowToJsonLd(howto: {
  name: string;
  description: string;
  totalTime?: string;
  steps: Array<{ name: string; text: string; url?: string }>;
}) {
  return {
    "@context": "https://schema.org",
    "@type": "HowTo",
    name: howto.name,
    description: howto.description,
    ...(howto.totalTime && { totalTime: howto.totalTime }),
    step: howto.steps.map((s, i) => ({
      "@type": "HowToStep",
      position: i + 1,
      name: s.name,
      text: s.text,
      ...(s.url && { url: s.url }),
    })),
  };
}
