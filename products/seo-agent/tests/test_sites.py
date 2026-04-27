from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sites.faccel import FaccelSite
from sites.saimu_times import SaimuTimesSite


def test_faccel_parses_frontmatter(tmp_path: Path):
    md = tmp_path / "sokujitsu.md"
    md.write_text(
        textwrap.dedent(
            """
            ---
            title: ファクタリング即日入金ガイド
            description: 即日入金の方法
            date: 2026-04-01
            category: ガイド
            author: ファクセル編集部
            keywords:
              - ファクタリング
              - 即日
            ---

            本文。
            """
        ).strip(),
        encoding="utf-8",
    )

    site = FaccelSite(content_dir=tmp_path)
    articles = site.list_articles()
    assert len(articles) == 1
    art = articles[0]
    assert art.slug == "sokujitsu"
    assert art.title == "ファクタリング即日入金ガイド"
    assert art.url == "https://faccel.jp/articles/sokujitsu"
    assert art.keywords == ["ファクタリング", "即日"]


def test_faccel_find_by_url(tmp_path: Path):
    (tmp_path / "kaikei.md").write_text(
        "---\ntitle: 会計\n---\n本文",
        encoding="utf-8",
    )
    site = FaccelSite(content_dir=tmp_path)
    found = site.find_article_by_url("https://faccel.jp/articles/kaikei")
    assert found is not None
    assert found.slug == "kaikei"

    missing = site.find_article_by_url("https://faccel.jp/articles/missing")
    assert missing is None


def test_saimu_parses_hugo_frontmatter(tmp_path: Path):
    guide_dir = tmp_path / "guide"
    guide_dir.mkdir()
    (guide_dir / "yamikin-bengoshi.md").write_text(
        textwrap.dedent(
            """
            ---
            title: 闇金は弁護士に
            slug: yamikin-bengoshi
            date: 2026-04-25
            categories:
              - 債務整理ガイド
            tags:
              - 闇金
              - 弁護士
            ---

            本文。
            """
        ).strip(),
        encoding="utf-8",
    )

    site = SaimuTimesSite(content_dir=tmp_path)
    articles = site.list_articles()
    assert len(articles) == 1
    art = articles[0]
    assert art.slug == "yamikin-bengoshi"
    assert art.url == "https://saimu-times.com/guide/yamikin-bengoshi/"
    assert art.keywords == ["闇金", "弁護士"]
    assert art.section == "債務整理ガイド"


def test_saimu_skips_top_level_pages(tmp_path: Path):
    (tmp_path / "about.md").write_text("---\ntitle: about\n---\n", encoding="utf-8")
    site = SaimuTimesSite(content_dir=tmp_path)
    assert site.list_articles() == []
