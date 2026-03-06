"""競合分析 API"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException

from config import COMPETITOR_CACHE_TTL_HOURS
from database.crud import (
    AsyncSessionLocal,
    get_cached_competitor,
    get_listing_by_sku,
    save_competitor_cache,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/competitor", tags=["competitor"])


@router.post("/{sku}")
async def run_competitor_analysis(sku: str):
    """出品の競合分析を実行"""
    from ebay.competitor import search_competitors, analyze_competitor_keywords

    async with AsyncSessionLocal() as session:
        listing = await get_listing_by_sku(session, sku)
        if listing is None:
            raise HTTPException(status_code=404, detail="Listing not found")

        # キャッシュチェック
        cached = await get_cached_competitor(
            session, listing.title, listing.category_id, COMPETITOR_CACHE_TTL_HOURS
        )
        if cached:
            return {
                "sku": sku,
                "cached": True,
                "competitors": json.loads(cached.results_json),
                "keyword_analysis": json.loads(cached.keyword_analysis_json),
            }

        # 新規分析
        try:
            competitors = await search_competitors(
                listing.title, listing.category_id
            )
            analysis = analyze_competitor_keywords(competitors, listing.title)
        except Exception as e:
            logger.error(f"競合分析失敗 {sku}: {e}")
            raise HTTPException(status_code=502, detail=str(e))

        # キャッシュ保存
        competitors_data = [c.__dict__ for c in competitors]
        await save_competitor_cache(
            session,
            query=listing.title,
            category_id=listing.category_id,
            results_json=json.dumps(competitors_data, ensure_ascii=False),
            keyword_analysis_json=json.dumps(analysis, ensure_ascii=False),
        )

        return {
            "sku": sku,
            "cached": False,
            "competitors": competitors_data,
            "keyword_analysis": analysis,
        }


@router.get("/{sku}")
async def get_competitor_cache(sku: str):
    """キャッシュされた競合分析結果を返す"""
    async with AsyncSessionLocal() as session:
        listing = await get_listing_by_sku(session, sku)
        if listing is None:
            raise HTTPException(status_code=404, detail="Listing not found")

        cached = await get_cached_competitor(
            session, listing.title, listing.category_id, COMPETITOR_CACHE_TTL_HOURS
        )
        if cached is None:
            return {"sku": sku, "cached": False, "competitors": [], "keyword_analysis": {}}

        return {
            "sku": sku,
            "cached": True,
            "competitors": json.loads(cached.results_json),
            "keyword_analysis": json.loads(cached.keyword_analysis_json),
        }
