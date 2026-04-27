import type { MetadataRoute } from "next";

const AI_BOTS_ALLOW = [
  "GPTBot",
  "OAI-SearchBot",
  "ChatGPT-User",
  "ClaudeBot",
  "Claude-Web",
  "anthropic-ai",
  "Google-Extended",
  "PerplexityBot",
  "Perplexity-User",
  "CCBot",
  "Applebot-Extended",
];

export default function robots(): MetadataRoute.Robots {
  const baseUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://faccel.jp";
  return {
    rules: [
      ...AI_BOTS_ALLOW.map((bot) => ({
        userAgent: bot,
        allow: "/",
        disallow: ["/api/", "/admin/", "/go/"],
      })),
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/api/", "/admin/"],
      },
    ],
    sitemap: `${baseUrl}/sitemap.xml`,
  };
}
