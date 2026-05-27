"""ストアセクションのキーワード分類ロジック。純粋関数のみ — 外部 API 呼び出しなし。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class Section:
    section_id: str
    name: str
    keywords: list[str]
    parent_id: str = ""


def load_rules(yaml_path: Path) -> list[Section]:
    """YAML ファイルからセクションルールを読み込む。"""
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return load_rules_from_dict(data)


def load_rules_from_dict(data: dict) -> list[Section]:
    """辞書からセクションルールを構築する（テスト用）。"""
    sections: list[Section] = []

    def _parse(raw_list: list[dict], parent_id: str = "") -> None:
        for item in raw_list:
            kws = [k.strip().lower() for k in item.get("keywords", [])]
            sections.append(
                Section(
                    section_id=item["id"],
                    name=item["name"],
                    keywords=kws,
                    parent_id=parent_id,
                )
            )
            for sub in item.get("subcategories", []):
                _parse([sub], parent_id=item["id"])

    _parse(data.get("sections", []))
    return sections


def classify_title(title: str, sections: list[Section]) -> Optional[Section]:
    """タイトルをキーワードマッチで分類する。

    サブカテゴリー（parent_id あり）を先に評価し、より具体的なセクションを優先する。
    どのキーワードにも一致しない場合は None を返す。
    """
    title_lower = title.lower()

    subcategories = [s for s in sections if s.parent_id]
    top_level = [s for s in sections if not s.parent_id]

    for section in subcategories + top_level:
        if any(kw in title_lower for kw in section.keywords):
            return section

    return None
