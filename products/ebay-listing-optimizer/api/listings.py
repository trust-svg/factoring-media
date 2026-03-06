"""出品管理 API"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException

from database.crud import (
    AsyncSessionLocal,
    get_all_listings,
    get_latest_score,
    get_listing_by_sku,
    get_listing_count,
    upsert_listing,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/listings", tags=["listings"])


@router.post("/fetch")
async def fetch_listings():
    """eBayからアクティブ出品を取得してDBに保存"""
    from ebay.listings import fetch_all_active_listings

    try:
        items = await fetch_all_active_listings()
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    async with AsyncSessionLocal() as session:
        for item in items:
            await upsert_listing(session, **item)

    return {"status": "ok", "count": len(items)}


@router.get("")
async def list_listings():
    """全出品を最新スコア付きで返す"""
    async with AsyncSessionLocal() as session:
        listings = await get_all_listings(session)
        result = []
        for listing in listings:
            score = await get_latest_score(session, listing.sku)
            result.append({
                "sku": listing.sku,
                "listing_id": listing.listing_id,
                "title": listing.title,
                "price_usd": listing.price_usd,
                "quantity": listing.quantity,
                "category_name": listing.category_name,
                "condition": listing.condition,
                "image_urls": json.loads(listing.image_urls_json),
                "fetched_at": listing.fetched_at.isoformat(),
                "score": {
                    "overall": score.overall_score,
                    "title": score.title_score,
                    "description": score.description_score,
                    "specifics": score.specifics_score,
                    "photos": score.photo_score,
                } if score else None,
            })
    return {"listings": result, "total": len(result)}


@router.get("/stats")
async def listing_stats():
    """サマリー統計を返す"""
    async with AsyncSessionLocal() as session:
        total = await get_listing_count(session)
        listings = await get_all_listings(session)
        low_score = 0
        scored = 0
        for listing in listings:
            score = await get_latest_score(session, listing.sku)
            if score:
                scored += 1
                if score.overall_score < 50:
                    low_score += 1
    return {
        "total": total,
        "scored": scored,
        "low_score_count": low_score,
    }


@router.get("/{sku}")
async def get_listing(sku: str):
    """単一出品の詳細を返す"""
    async with AsyncSessionLocal() as session:
        listing = await get_listing_by_sku(session, sku)
        if listing is None:
            raise HTTPException(status_code=404, detail="Listing not found")
        score = await get_latest_score(session, listing.sku)
        return {
            "sku": listing.sku,
            "listing_id": listing.listing_id,
            "title": listing.title,
            "description": listing.description,
            "price_usd": listing.price_usd,
            "quantity": listing.quantity,
            "category_id": listing.category_id,
            "category_name": listing.category_name,
            "condition": listing.condition,
            "image_urls": json.loads(listing.image_urls_json),
            "item_specifics": json.loads(listing.item_specifics_json),
            "offer_id": listing.offer_id,
            "fetched_at": listing.fetched_at.isoformat(),
            "score": {
                "overall": score.overall_score,
                "title": score.title_score,
                "description": score.description_score,
                "specifics": score.specifics_score,
                "photos": score.photo_score,
                "issues": json.loads(score.issues_json),
                "suggestions": json.loads(score.suggestions_json),
                "scored_at": score.scored_at.isoformat(),
            } if score else None,
        }
