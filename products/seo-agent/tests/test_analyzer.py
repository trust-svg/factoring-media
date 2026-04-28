from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.analyzer import (
    affiliate_funnel_only,
    classify,
    classify_tier,
    classify_trend,
    is_affiliate_funnel_url,
    split_by_tier,
)


def _row(keyword: str, page: str, position: float, impressions: int = 100, clicks: int = 5) -> dict:
    return {
        "keyword": keyword,
        "page": page,
        "impressions": impressions,
        "clicks": clicks,
        "ctr": clicks / impressions if impressions else 0.0,
        "position": position,
    }


def test_classify_tier_rewrite():
    assert classify_tier(5.0) == "rewrite"
    assert classify_tier(15.0) == "rewrite"
    assert classify_tier(29.9) == "rewrite"


def test_classify_tier_title():
    assert classify_tier(30.0) == "title"
    assert classify_tier(45.0) == "title"
    assert classify_tier(59.9) == "title"


def test_classify_tier_seed():
    assert classify_tier(60.0) == "seed"
    assert classify_tier(80.0) == "seed"
    assert classify_tier(100.0) == "seed"


def test_classify_tier_out_of_range():
    assert classify_tier(3.0) is None
    assert classify_tier(101.0) is None


def test_classify_trend():
    assert classify_trend(None, 2.0, 1.0) == "stagnant"
    assert classify_trend(2.5, 2.0, 1.0) == "declining"
    assert classify_trend(-1.5, 2.0, 1.0) == "rising"
    assert classify_trend(0.5, 2.0, 1.0) == "stagnant"


def test_is_affiliate_funnel_url():
    assert is_affiliate_funnel_url("https://faccel.jp/companies/paytner")
    assert is_affiliate_funnel_url("https://faccel.jp/articles/foo/reviews")
    assert is_affiliate_funnel_url("https://faccel.jp/go/paytner")
    assert not is_affiliate_funnel_url("https://faccel.jp/articles/sokujitsu")


def test_filters_out_below_5():
    insights = classify(
        [_row("a", "/p", position=3.5)],
        previous_lookup=lambda *_: None,
    )
    assert insights == []


def test_filters_out_above_100():
    insights = classify(
        [_row("a", "/p", position=120.0)],
        previous_lookup=lambda *_: None,
    )
    assert insights == []


def test_filters_low_impressions():
    insights = classify(
        [_row("a", "/p", position=10.0, impressions=5, clicks=0)],
        previous_lookup=lambda *_: None,
        min_impressions=10,
    )
    assert insights == []


def test_classifies_into_rewrite_tier():
    insights = classify(
        [_row("a", "/p", position=12.0)],
        previous_lookup=lambda *_: None,
        min_impressions=10,
    )
    assert len(insights) == 1
    assert insights[0].tier == "rewrite"


def test_classifies_into_title_tier():
    insights = classify(
        [_row("a", "/p", position=42.0)],
        previous_lookup=lambda *_: None,
        min_impressions=10,
    )
    assert insights[0].tier == "title"


def test_classifies_into_seed_tier():
    insights = classify(
        [_row("a", "/p", position=80.0)],
        previous_lookup=lambda *_: None,
        min_impressions=10,
    )
    assert insights[0].tier == "seed"


def test_trend_declining_when_position_worsens():
    insights = classify(
        [_row("a", "/p", position=12.0)],
        previous_lookup=lambda *_: 8.0,
        min_impressions=10,
    )
    assert insights[0].trend == "declining"
    assert insights[0].delta == 4.0


def test_trend_rising_when_position_improves():
    insights = classify(
        [_row("a", "/p", position=8.0)],
        previous_lookup=lambda *_: 12.0,
        min_impressions=10,
    )
    assert insights[0].trend == "rising"


def test_trend_stagnant_with_no_history():
    insights = classify(
        [_row("a", "/p", position=10.0)],
        previous_lookup=lambda *_: None,
        min_impressions=10,
    )
    assert insights[0].trend == "stagnant"


def test_split_by_tier():
    rows = [
        _row("rw_kw", "/p1", position=12.0),
        _row("ti_kw", "/p2", position=45.0),
        _row("se_kw", "/p3", position=80.0),
    ]
    insights = classify(rows, previous_lookup=lambda *_: None, min_impressions=10)
    buckets = split_by_tier(insights)
    assert len(buckets["rewrite"]) == 1
    assert len(buckets["title"]) == 1
    assert len(buckets["seed"]) == 1


def test_affiliate_flag_set():
    insights = classify(
        [_row("a", "/companies/paytner", position=15.0)],
        previous_lookup=lambda *_: None,
        min_impressions=10,
    )
    assert insights[0].is_affiliate_funnel is True


def test_affiliate_funnel_only_filter():
    rows = [
        _row("normal", "/articles/sokujitsu", position=15.0),
        _row("aff", "/companies/paytner", position=20.0),
    ]
    insights = classify(rows, previous_lookup=lambda *_: None, min_impressions=10)
    aff = affiliate_funnel_only(insights)
    assert len(aff) == 1
    assert aff[0].keyword == "aff"


def test_ctr_zero_warning_only_for_top_30():
    rows = [
        _row("top", "/p1", position=12.0, impressions=100, clicks=0),
        _row("bottom", "/p2", position=80.0, impressions=100, clicks=0),
    ]
    insights = classify(rows, previous_lookup=lambda *_: None, min_impressions=10)
    by_kw = {i.keyword: i for i in insights}
    assert by_kw["top"].ctr_zero_warning is True
    assert by_kw["bottom"].ctr_zero_warning is False


def test_sorts_by_impressions_desc():
    rows = [
        _row("low", "/p1", position=10.0, impressions=60),
        _row("high", "/p2", position=10.0, impressions=500),
    ]
    insights = classify(rows, previous_lookup=lambda *_: None, min_impressions=10)
    assert insights[0].keyword == "high"
    assert insights[1].keyword == "low"
