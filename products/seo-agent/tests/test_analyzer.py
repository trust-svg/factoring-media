from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.analyzer import classify, split_by_category


def _row(keyword: str, page: str, position: float, impressions: int = 100, clicks: int = 5) -> dict:
    return {
        "keyword": keyword,
        "page": page,
        "impressions": impressions,
        "clicks": clicks,
        "ctr": clicks / impressions if impressions else 0.0,
        "position": position,
    }


def test_filters_out_top_5():
    insights = classify(
        [_row("a", "/p", position=3.5)],
        previous_lookup=lambda *_: None,
    )
    assert insights == []


def test_filters_out_below_20():
    insights = classify(
        [_row("a", "/p", position=25.0)],
        previous_lookup=lambda *_: None,
    )
    assert insights == []


def test_filters_low_impressions():
    insights = classify(
        [_row("a", "/p", position=10.0, impressions=10, clicks=0)],
        previous_lookup=lambda *_: None,
    )
    assert insights == []


def test_classifies_declining():
    insights = classify(
        [_row("a", "/p", position=12.0)],
        previous_lookup=lambda kw, page: 8.0,
    )
    assert len(insights) == 1
    assert insights[0].category == "declining"
    assert insights[0].delta == 4.0


def test_classifies_rising():
    insights = classify(
        [_row("a", "/p", position=8.0)],
        previous_lookup=lambda kw, page: 12.0,
    )
    assert insights[0].category == "rising"


def test_classifies_stagnant_when_no_history():
    insights = classify(
        [_row("a", "/p", position=10.0)],
        previous_lookup=lambda *_: None,
    )
    assert insights[0].category == "stagnant"


def test_split_by_category():
    rows = [
        _row("rising_kw", "/p1", position=8.0),
        _row("declining_kw", "/p2", position=15.0),
        _row("stagnant_kw", "/p3", position=11.0),
    ]

    def lookup(kw: str, page: str) -> float | None:
        return {"rising_kw": 12.0, "declining_kw": 8.0}.get(kw)

    insights = classify(rows, previous_lookup=lookup)
    buckets = split_by_category(insights)
    assert len(buckets["rising"]) == 1
    assert len(buckets["declining"]) == 1
    assert len(buckets["stagnant"]) == 1


def test_sorts_by_impressions_desc():
    rows = [
        _row("low", "/p1", position=10.0, impressions=60),
        _row("high", "/p2", position=10.0, impressions=500),
    ]
    insights = classify(rows, previous_lookup=lambda *_: None)
    assert insights[0].keyword == "high"
    assert insights[1].keyword == "low"
