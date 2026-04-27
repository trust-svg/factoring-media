from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import frontmatter

from core.sites import Article


class FaccelSite:
    name = "faccel"
    domain = os.getenv("FACCEL_DOMAIN", "faccel.jp")
    gsc_property = os.getenv("FACCEL_GSC_PROPERTY", "sc-domain:faccel.jp")

    def __init__(self, content_dir: Path | None = None) -> None:
        self.content_dir = content_dir or Path(
            os.getenv("FACCEL_CONTENT_DIR", "/host/factoring-media/content/articles")
        )

    def list_articles(self) -> list[Article]:
        if not self.content_dir.exists():
            return []
        articles: list[Article] = []
        for md_path in sorted(self.content_dir.glob("*.md")):
            try:
                post = frontmatter.load(md_path)
            except Exception:
                continue
            slug = md_path.stem
            data = post.metadata or {}
            articles.append(
                Article(
                    slug=slug,
                    title=str(data.get("title") or ""),
                    path=md_path,
                    url=f"https://{self.domain}/articles/{slug}",
                    keywords=list(data.get("keywords") or []),
                    published_at=str(data.get("date") or "") or None,
                    section=str(data.get("category") or "") or None,
                )
            )
        return articles

    def find_article_by_url(self, url: str) -> Article | None:
        path = urlparse(url).path.rstrip("/")
        if not path.startswith("/articles/"):
            return None
        slug = path.removeprefix("/articles/").split("/")[0]
        md_path = self.content_dir / f"{slug}.md"
        if not md_path.exists():
            return None
        for art in self.list_articles():
            if art.slug == slug:
                return art
        return None
