from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

Tier = Literal["rewrite", "title", "seed"]
Trend = Literal["rising", "stagnant", "declining"]


@dataclass
class KeywordInsight:
    keyword: str
    page: str
    impressions: int
    clicks: int
    ctr: float
    position: float
    previous_position: float | None
    delta: float | None
    tier: Tier
    trend: Trend
    is_affiliate_funnel: bool
    ctr_zero_warning: bool


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


def classify_tier(position: float) -> Tier | None:
    if 5.0 <= position < 30.0:
        return "rewrite"
    if 30.0 <= position < 60.0:
        return "title"
    if 60.0 <= position <= 100.0:
        return "seed"
    return None


def classify_trend(delta: float | None, declining_threshold: float, rising_threshold: float) -> Trend:
    if delta is None:
        return "stagnant"
    if delta >= declining_threshold:
        return "declining"
    if delta <= -rising_threshold:
        return "rising"
    return "stagnant"


def is_affiliate_funnel_url(url: str) -> bool:
    return "/companies/" in url or "/reviews" in url or "/go/" in url


def classify(
    rows: list[dict],
    *,
    previous_lookup,
    position_min: float | None = None,
    position_max: float | None = None,
    min_impressions: int | None = None,
    declining_threshold: float = 2.0,
    rising_threshold: float = 1.0,
) -> list[KeywordInsight]:
    pos_min = position_min if position_min is not None else _env_float("POSITION_MIN", 5.0)
    pos_max = position_max if position_max is not None else _env_float("POSITION_MAX", 100.0)
    imp_min = min_impressions if min_impressions is not None else _env_int("MIN_IMPRESSIONS", 10)

    out: list[KeywordInsight] = []
    for r in rows:
        position = float(r["position"])
        impressions = int(r["impressions"])
        clicks = int(r["clicks"])
        if not (pos_min <= position <= pos_max):
            continue
        if impressions < imp_min:
            continue

        tier = classify_tier(position)
        if tier is None:
            continue

        prev = previous_lookup(r["keyword"], r["page"])
        delta = (position - prev) if prev is not None else None
        trend = classify_trend(delta, declining_threshold, rising_threshold)

        out.append(
            KeywordInsight(
                keyword=r["keyword"],
                page=r["page"],
                impressions=impressions,
                clicks=clicks,
                ctr=float(r["ctr"]),
                position=position,
                previous_position=prev,
                delta=delta,
                tier=tier,
                trend=trend,
                is_affiliate_funnel=is_affiliate_funnel_url(r["page"]),
                ctr_zero_warning=(impressions >= imp_min and clicks == 0 and position < 30.0),
            )
        )

    out.sort(key=lambda i: (-i.impressions, i.position))
    return out


def split_by_tier(insights: list[KeywordInsight]) -> dict[Tier, list[KeywordInsight]]:
    buckets: dict[Tier, list[KeywordInsight]] = {
        "rewrite": [],
        "title": [],
        "seed": [],
    }
    for i in insights:
        buckets[i.tier].append(i)
    return buckets


def affiliate_funnel_only(insights: list[KeywordInsight]) -> list[KeywordInsight]:
    return [i for i in insights if i.is_affiliate_funnel]
