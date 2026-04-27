from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

Category = Literal["rising", "stagnant", "declining"]


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
    category: Category


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


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
    pos_max = position_max if position_max is not None else _env_float("POSITION_MAX", 20.0)
    imp_min = min_impressions if min_impressions is not None else _env_int("MIN_IMPRESSIONS", 50)

    out: list[KeywordInsight] = []
    for r in rows:
        position = float(r["position"])
        impressions = int(r["impressions"])
        if not (pos_min <= position <= pos_max):
            continue
        if impressions < imp_min:
            continue

        prev = previous_lookup(r["keyword"], r["page"])
        delta = (position - prev) if prev is not None else None

        category: Category
        if delta is not None and delta >= declining_threshold:
            category = "declining"
        elif delta is not None and delta <= -rising_threshold:
            category = "rising"
        else:
            category = "stagnant"

        out.append(
            KeywordInsight(
                keyword=r["keyword"],
                page=r["page"],
                impressions=impressions,
                clicks=int(r["clicks"]),
                ctr=float(r["ctr"]),
                position=position,
                previous_position=prev,
                delta=delta,
                category=category,
            )
        )

    out.sort(key=lambda i: (-i.impressions, i.position))
    return out


def split_by_category(insights: list[KeywordInsight]) -> dict[Category, list[KeywordInsight]]:
    buckets: dict[Category, list[KeywordInsight]] = {
        "declining": [],
        "stagnant": [],
        "rising": [],
    }
    for i in insights:
        buckets[i.category].append(i)
    return buckets
