"""eBay Browse API を使った競合分析"""
from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter
from dataclasses import dataclass

import requests

from config import EBAY_API_BASE, EBAY_API_CALLS_PER_SECOND
from ebay.auth import get_auth_headers

logger = logging.getLogger(__name__)


@dataclass
class CompetitorListing:
    item_id: str
    title: str
    price_usd: float
    sold_quantity: int
    category_id: str
    item_specifics: dict[str, str]
    image_count: int


# タイトルから除外する一般的な語
_STOP_WORDS = {
    "the", "a", "an", "and", "or", "for", "with", "from", "in", "on", "to",
    "of", "is", "it", "by", "at", "as", "w/", "-", "/", "&", "+",
    "new", "used", "free", "shipping", "fast",
}


async def search_competitors(
    query: str, category_id: str, limit: int = 20
) -> list[CompetitorListing]:
    """Browse API で類似商品を検索し、売れ筋順で返す"""
    headers = get_auth_headers()
    delay = 1.0 / EBAY_API_CALLS_PER_SECOND

    # クエリからブランド名+モデル名を抽出（最初の数語）
    search_terms = query.split()[:5]
    search_query = " ".join(search_terms)

    url = f"{EBAY_API_BASE}/buy/browse/v1/item_summary/search"
    params = {
        "q": search_query,
        "limit": min(limit, 50),
        "sort": "price",
        "filter": "buyingOptions:{FIXED_PRICE}",
    }
    if category_id:
        params["category_ids"] = category_id

    resp = requests.get(url, headers=headers, params=params, timeout=30)
    if resp.status_code != 200:
        logger.warning(f"競合検索失敗: {resp.status_code} - {resp.text[:200]}")
        return []

    data = resp.json()
    results = []

    for item in data.get("itemSummaries", []):
        price_data = item.get("price", {})
        price = float(price_data.get("value", 0.0))

        results.append(CompetitorListing(
            item_id=item.get("itemId", ""),
            title=item.get("title", ""),
            price_usd=price,
            sold_quantity=0,
            category_id=item.get("categories", [{}])[0].get("categoryId", "") if item.get("categories") else "",
            item_specifics={},
            image_count=len(item.get("additionalImages", [])) + (1 if item.get("image") else 0),
        ))

    await asyncio.sleep(delay)
    logger.info(f"競合 {len(results)} 件を取得: '{search_query}'")
    return results


def analyze_competitor_keywords(
    competitors: list[CompetitorListing], own_title: str
) -> dict:
    """競合タイトルからキーワード分析を行う"""
    if not competitors:
        return {
            "top_keywords": [],
            "avg_title_length": 0,
            "avg_price": 0,
            "missing_keywords": [],
        }

    all_keywords: list[str] = []
    for comp in competitors:
        words = _extract_keywords(comp.title)
        all_keywords.extend(words)

    keyword_counts = Counter(all_keywords)
    # 出現2回以上のキーワードを頻度順で
    top_keywords = [
        (kw, count) for kw, count in keyword_counts.most_common(20)
        if count >= 2
    ]

    own_words = set(_extract_keywords(own_title))
    missing = [
        kw for kw, count in top_keywords
        if kw.lower() not in {w.lower() for w in own_words}
    ]

    avg_title_length = sum(len(c.title) for c in competitors) / len(competitors)
    avg_price = sum(c.price_usd for c in competitors) / len(competitors)

    return {
        "top_keywords": top_keywords,
        "avg_title_length": round(avg_title_length, 1),
        "avg_price": round(avg_price, 2),
        "missing_keywords": missing[:10],
    }


def _extract_keywords(title: str) -> list[str]:
    """タイトルからキーワードを抽出する"""
    # 記号を除去してスプリット
    cleaned = re.sub(r'[^\w\s/\-&+]', ' ', title)
    words = cleaned.split()
    return [
        w for w in words
        if w.lower() not in _STOP_WORDS and len(w) >= 2
    ]
