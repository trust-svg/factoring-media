import fs from "fs";
import path from "path";
import matter from "gray-matter";

export const dynamic = "force-static";
export const revalidate = 3600;

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://faccel.jp";
const SITE_NAME = "FACCEL";
const SUMMARY =
  "中小企業・個人事業主向けにファクタリング（請求書買取による資金調達）の仕組み、業者比較、活用事例を解説する情報メディア。";

export async function GET() {
  const articlesDir = path.join(process.cwd(), "content/articles");
  const fileNames = fs
    .readdirSync(articlesDir)
    .filter((f) => f.endsWith(".md"));

  const articles = fileNames
    .map((fileName) => {
      const slug = fileName.replace(/\.md$/, "");
      const fullPath = path.join(articlesDir, fileName);
      const raw = fs.readFileSync(fullPath, "utf8");
      const { data, content } = matter(raw);
      return {
        slug,
        title: data.title || "",
        description: data.description || "",
        date: data.date || "",
        category: data.category || "",
        author: data.author || "",
        content: content.trim(),
      };
    })
    .sort((a, b) => (a.date > b.date ? -1 : 1));

  const lines: string[] = [];
  lines.push(`# ${SITE_NAME} (full content)`);
  lines.push("");
  lines.push(`> ${SUMMARY}`);
  lines.push("");
  lines.push(
    `本ファイルは AI 検索エンジン（ChatGPT/Claude/Perplexity/Gemini 等）向けに、サイトの主要記事を Markdown で連結したものです。`
  );
  lines.push("");

  for (const a of articles) {
    lines.push("---");
    lines.push("");
    lines.push(`## ${a.title}`);
    lines.push(`URL: ${SITE_URL}/articles/${a.slug}`);
    if (a.date) lines.push(`公開日: ${a.date}`);
    if (a.category) lines.push(`カテゴリ: ${a.category}`);
    if (a.author) lines.push(`著者: ${a.author}`);
    lines.push("");
    if (a.description) {
      lines.push(`> ${a.description}`);
      lines.push("");
    }
    lines.push(a.content);
    lines.push("");
  }

  lines.push("---");
  lines.push("");
  lines.push(`最終更新: ${new Date().toISOString().slice(0, 10)}`);

  return new Response(lines.join("\n"), {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, max-age=3600, s-maxage=3600",
    },
  });
}
