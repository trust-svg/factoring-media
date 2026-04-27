from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import frontmatter

from core.sites import Article


SECTIONS = ("post", "guide", "knowledge", "taikendan")


class SaimuTimesSite:
    name = "saimu_times"
    domain = os.getenv("SAIMU_DOMAIN", "saimu-times.com")
    gsc_property = os.getenv("SAIMU_GSC_PROPERTY", "sc-domain:saimu-times.com")

    def __init__(self, content_dir: Path | None = None) -> None:
        self.content_dir = content_dir or Path(
            os.getenv("SAIMU_CONTENT_DIR", "/host/saimu-media/site/content")
        )

    def list_articles(self) -> list[Article]:
        if not self.content_dir.exists():
            return []
        articles: list[Article] = []
        for section in SECTIONS:
            section_dir = self.content_dir / section
            if not section_dir.exists():
                continue
            for md_path in sorted(section_dir.rglob("*.md")):
                if md_path.stem.startswith("_"):
                    continue
                try:
                    post = frontmatter.load(md_path)
                except Exception:
                    continue
                data = post.metadata or {}
                slug = data.get("slug") or md_path.stem
                tags = list(data.get("tags") or [])
                categories = list(data.get("categories") or [])
                articles.append(
                    Article(
                        slug=str(slug),
                        title=str(data.get("title") or ""),
                        path=md_path,
                        url=f"https://{self.domain}/{section}/{slug}/",
                        keywords=tags,
                        published_at=str(data.get("date") or "") or None,
                        section=categories[0] if categories else section,
                    )
                )
        return articles

    def find_article_by_url(self, url: str) -> Article | None:
        path = urlparse(url).path.strip("/")
        parts = path.split("/")
        if len(parts) < 2 or parts[0] not in SECTIONS:
            return None
        section, slug = parts[0], parts[1]
        for art in self.list_articles():
            if art.section == section and art.slug == slug:
                return art
            if art.url.rstrip("/").endswith(f"/{section}/{slug}"):
                return art
        return None
