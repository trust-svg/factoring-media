from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class Article:
    slug: str
    title: str
    path: Path
    url: str
    keywords: list[str] = field(default_factory=list)
    published_at: str | None = None
    section: str | None = None


class Site(Protocol):
    name: str
    domain: str
    gsc_property: str
    content_dir: Path

    def list_articles(self) -> list[Article]: ...

    def find_article_by_url(self, url: str) -> Article | None: ...
