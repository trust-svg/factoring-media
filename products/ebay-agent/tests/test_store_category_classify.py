"""store_category_classify.py の単体テスト"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scripts.store_category_classify import (
    Section,
    load_rules_from_dict,
    classify_title,
)

# ── テスト用ルール定義 ────────────────────────────────────

RULES_DICT = {
    "sections": [
        {
            "id": "100",
            "name": "Watches",
            "keywords": ["watch", "seiko", "casio"],
            "subcategories": [
                {"id": "101", "name": "Luxury Watches", "keywords": ["rolex", "omega"]},
            ],
        },
        {
            "id": "200",
            "name": "Cameras",
            "keywords": ["camera", "nikon", "canon", "lens"],
        },
    ]
}


@pytest.fixture
def sections():
    return load_rules_from_dict(RULES_DICT)


# ── load_rules_from_dict ─────────────────────────────────


def test_load_rules_top_level_count(sections):
    # サブカテゴリーも含めてフラットに返す: Watches + Luxury Watches + Cameras = 3
    assert len(sections) == 3


def test_load_rules_subcategory_has_parent(sections):
    luxury = next(s for s in sections if s.name == "Luxury Watches")
    assert luxury.parent_id == "100"


def test_load_rules_top_level_no_parent(sections):
    cameras = next(s for s in sections if s.name == "Cameras")
    assert cameras.parent_id == ""


# ── classify_title ───────────────────────────────────────


def test_classify_exact_keyword(sections):
    result = classify_title("Seiko Presage SARX055 Automatic", sections)
    assert result is not None
    assert result.name == "Watches"


def test_classify_case_insensitive(sections):
    result = classify_title("CANON EF 50mm f/1.8 STM Lens", sections)
    assert result is not None
    assert result.name == "Cameras"


def test_classify_subcategory_wins(sections):
    # "rolex" は Luxury Watches のキーワード → Luxury Watches が返る（Watches ではない）
    result = classify_title("Rolex Submariner 116610LN", sections)
    assert result is not None
    assert result.name == "Luxury Watches"


def test_classify_no_match(sections):
    result = classify_title("Unknown Widget XYZ-999", sections)
    assert result is None


def test_classify_partial_word_match(sections):
    # "wristwatch" contains "watch" → matches Watches
    result = classify_title("Vintage Wristwatch 1960s", sections)
    assert result is not None
    assert result.name == "Watches"
