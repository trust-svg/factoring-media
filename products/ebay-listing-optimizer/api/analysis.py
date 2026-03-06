"""SEO分析 API"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException

from database.crud import (
    AsyncSessionLocal,
    get_all_listings,
    get_latest_score,
    get_listing_by_sku,
    save_seo_score,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.post("/{sku}")
async def analyze_listing(sku: str):
    """単一出品のSEO分析を実行"""
    from analyzer.scorer import score_listing

    async with AsyncSessionLocal() as session:
        listing = await get_listing_by_sku(session, sku)
        if listing is None:
            raise HTTPException(status_code=404, detail="Listing not found")

        result = score_listing(listing)
        score = await save_seo_score(
            session,
            sku=sku,
            overall_score=result["overall"],
            title_score=result["title_score"],
            description_score=result["description_score"],
            specifics_score=result["specifics_score"],
            photo_score=result["photo_score"],
            issues_json=json.dumps(result["issues"], ensure_ascii=False),
            suggestions_json=json.dumps(result["suggestions"], ensure_ascii=False),
        )
        return {
            "sku": sku,
            "score": {
                "overall": score.overall_score,
                "title": score.title_score,
                "description": score.description_score,
                "specifics": score.specifics_score,
                "photos": score.photo_score,
                "issues": result["issues"],
                "suggestions": result["suggestions"],
            },
        }


@router.post("/batch")
async def analyze_batch():
    """全出品のSEO分析を一括実行"""
    from analyzer.scorer import score_listing

    async with AsyncSessionLocal() as session:
        listings = await get_all_listings(session)
        results = []
        for listing in listings:
            result = score_listing(listing)
            await save_seo_score(
                session,
                sku=listing.sku,
                overall_score=result["overall"],
                title_score=result["title_score"],
                description_score=result["description_score"],
                specifics_score=result["specifics_score"],
                photo_score=result["photo_score"],
                issues_json=json.dumps(result["issues"], ensure_ascii=False),
                suggestions_json=json.dumps(result["suggestions"], ensure_ascii=False),
            )
            results.append({
                "sku": listing.sku,
                "title": listing.title,
                "overall_score": result["overall"],
            })
    return {"analyzed": len(results), "results": results}
