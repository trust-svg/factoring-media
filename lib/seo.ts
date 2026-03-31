import type { Metadata } from "next";

const SITE_NAME = "ファクタリングの窓口";
const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://factoring-navi.com";
const DEFAULT_DESCRIPTION =
  "ファクタリング業者の口コミ・評判を比較。手数料・入金速度・審査の甘さで徹底比較。おすすめランキングや一括見積もりで最適な業者が見つかります。";

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
