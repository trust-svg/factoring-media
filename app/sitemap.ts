import { prisma } from "@/lib/prisma";
import type { MetadataRoute } from "next";

export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const baseUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://factoring-navi.com";

  const companies = await prisma.company.findMany({
    select: { slug: true, updatedAt: true },
  });

  const staticPages = [
    { url: baseUrl, lastModified: new Date(), changeFrequency: "weekly" as const, priority: 1 },
    { url: `${baseUrl}/companies`, lastModified: new Date(), changeFrequency: "weekly" as const, priority: 0.9 },
    { url: `${baseUrl}/ranking`, lastModified: new Date(), changeFrequency: "weekly" as const, priority: 0.9 },
    { url: `${baseUrl}/reviews`, lastModified: new Date(), changeFrequency: "daily" as const, priority: 0.8 },
    { url: `${baseUrl}/articles`, lastModified: new Date(), changeFrequency: "weekly" as const, priority: 0.7 },
    { url: `${baseUrl}/estimate`, lastModified: new Date(), changeFrequency: "monthly" as const, priority: 0.8 },
  ];

  const companyPages = companies.map((c) => ({
    url: `${baseUrl}/companies/${c.slug}`,
    lastModified: c.updatedAt,
    changeFrequency: "weekly" as const,
    priority: 0.8,
  }));

  const articleSlugs = ["what-is-factoring", "how-to-choose", "fee-comparison", "vs-bank-loan", "illegal-factoring"];
  const articlePages = articleSlugs.map((slug) => ({
    url: `${baseUrl}/articles/${slug}`,
    lastModified: new Date(),
    changeFrequency: "monthly" as const,
    priority: 0.6,
  }));

  return [...staticPages, ...companyPages, ...articlePages];
}
