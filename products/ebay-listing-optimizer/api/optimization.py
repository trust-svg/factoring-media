"""AI最適化 API"""
from __future__ import annotations

import json
import logging
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database.crud import (
    AsyncSessionLocal,
    get_all_listings,
    get_latest_optimization,
    get_latest_score,
    get_listing_by_sku,
    save_optimization,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/optimize", tags=["optimization"])


@router.post("/{sku}")
async def optimize_listing(sku: str):
    """単一出品のAI最適化を実行"""
    from analyzer.scorer import score_listing
    from optimizer.agent import run_optimizer

    async with AsyncSessionLocal() as session:
        listing = await get_listing_by_sku(session, sku)
        if listing is None:
            raise HTTPException(status_code=404, detail="Listing not found")

        # スコアを取得（なければ先に分析）
        score = await get_latest_score(session, sku)
        if score is None:
            score_data = score_listing(listing)
        else:
            score_data = {
                "overall": score.overall_score,
                "title_score": score.title_score,
                "description_score": score.description_score,
                "specifics_score": score.specifics_score,
                "photo_score": score.photo_score,
                "issues": json.loads(score.issues_json),
                "suggestions": json.loads(score.suggestions_json),
            }

        # AI最適化実行
        try:
            result = await run_optimizer(listing, score_data)
        except Exception as e:
            logger.error(f"AI最適化失敗 {sku}: {e}")
            raise HTTPException(status_code=502, detail=str(e))

        # 結果を保存
        opt = await save_optimization(
            session,
            sku=sku,
            original_title=listing.title,
            suggested_title=result["suggested_title"],
            original_description=listing.description,
            suggested_description=result.get("suggested_description"),
            suggested_specifics_json=json.dumps(
                result.get("suggested_specifics", {}), ensure_ascii=False
            ),
            reasoning=result.get("reasoning", ""),
            confidence=result.get("confidence", 0.0),
        )

        return {
            "sku": sku,
            "optimization_id": opt.id,
            "original_title": listing.title,
            "suggested_title": result["suggested_title"],
            "suggested_description": result.get("suggested_description"),
            "suggested_specifics": result.get("suggested_specifics", {}),
            "reasoning": result.get("reasoning", ""),
        }


class BatchOptimizeRequest(BaseModel):
    skus: List[str] = []


@router.post("/batch")
async def optimize_batch(body: BatchOptimizeRequest):
    """複数出品のAI最適化を一括実行"""
    from analyzer.scorer import score_listing
    from optimizer.agent import run_optimizer

    async with AsyncSessionLocal() as session:
        if body.skus:
            listings = []
            for sku in body.skus:
                listing = await get_listing_by_sku(session, sku)
                if listing:
                    listings.append(listing)
        else:
            listings = await get_all_listings(session)

        results = []
        for listing in listings:
            try:
                score_data = score_listing(listing)
                result = await run_optimizer(listing, score_data)
                await save_optimization(
                    session,
                    sku=listing.sku,
                    original_title=listing.title,
                    suggested_title=result["suggested_title"],
                    original_description=listing.description,
                    suggested_description=result.get("suggested_description"),
                    suggested_specifics_json=json.dumps(
                        result.get("suggested_specifics", {}), ensure_ascii=False
                    ),
                    reasoning=result.get("reasoning", ""),
                    confidence=result.get("confidence", 0.0),
                )
                results.append({
                    "sku": listing.sku,
                    "status": "ok",
                    "suggested_title": result["suggested_title"],
                })
            except Exception as e:
                logger.error(f"バッチ最適化失敗 {listing.sku}: {e}")
                results.append({
                    "sku": listing.sku,
                    "status": "error",
                    "error": str(e),
                })

    return {"optimized": len([r for r in results if r["status"] == "ok"]), "results": results}


@router.get("/{sku}/result")
async def get_optimization_result(sku: str):
    """最新の最適化結果を返す"""
    async with AsyncSessionLocal() as session:
        opt = await get_latest_optimization(session, sku)
        if opt is None:
            return {"sku": sku, "optimization": None}
        return {
            "sku": sku,
            "optimization": {
                "id": opt.id,
                "original_title": opt.original_title,
                "suggested_title": opt.suggested_title,
                "original_description": opt.original_description,
                "suggested_description": opt.suggested_description,
                "suggested_specifics": json.loads(opt.suggested_specifics_json),
                "reasoning": opt.reasoning,
                "confidence": opt.confidence,
                "status": opt.status,
                "created_at": opt.created_at.isoformat(),
            },
        }
