"""変更適用 API"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database.crud import (
    AsyncSessionLocal,
    get_change_history,
    get_latest_optimization,
    get_listing_by_sku,
    record_change,
    update_optimization_status,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/apply", tags=["apply"])


class ApplyRequest(BaseModel):
    apply_title: bool = False
    apply_description: bool = False
    apply_specifics: bool = False


@router.post("/{sku}")
async def apply_optimization(sku: str, body: ApplyRequest):
    """承認済み最適化をeBayに適用"""
    from ebay.updater import update_listing

    async with AsyncSessionLocal() as session:
        listing = await get_listing_by_sku(session, sku)
        if listing is None:
            raise HTTPException(status_code=404, detail="Listing not found")

        opt = await get_latest_optimization(session, sku)
        if opt is None:
            raise HTTPException(status_code=404, detail="No optimization found")

        changes_applied = []
        errors = []

        if body.apply_title and opt.suggested_title:
            try:
                success = await update_listing(
                    sku, title=opt.suggested_title
                )
                await record_change(
                    session,
                    sku=sku,
                    field_changed="title",
                    old_value=listing.title,
                    new_value=opt.suggested_title,
                    success=1 if success else 0,
                )
                if success:
                    changes_applied.append("title")
                else:
                    errors.append("title update failed")
            except Exception as e:
                await record_change(
                    session,
                    sku=sku,
                    field_changed="title",
                    old_value=listing.title,
                    new_value=opt.suggested_title,
                    success=0,
                    error_message=str(e),
                )
                errors.append(f"title: {e}")

        if body.apply_description and opt.suggested_description:
            try:
                success = await update_listing(
                    sku, description=opt.suggested_description
                )
                await record_change(
                    session,
                    sku=sku,
                    field_changed="description",
                    old_value=listing.description or "",
                    new_value=opt.suggested_description,
                    success=1 if success else 0,
                )
                if success:
                    changes_applied.append("description")
                else:
                    errors.append("description update failed")
            except Exception as e:
                await record_change(
                    session,
                    sku=sku,
                    field_changed="description",
                    old_value=listing.description or "",
                    new_value=opt.suggested_description,
                    success=0,
                    error_message=str(e),
                )
                errors.append(f"description: {e}")

        if body.apply_specifics:
            specifics = json.loads(opt.suggested_specifics_json)
            if specifics:
                try:
                    success = await update_listing(sku, item_specifics=specifics)
                    await record_change(
                        session,
                        sku=sku,
                        field_changed="specifics",
                        old_value=listing.item_specifics_json,
                        new_value=opt.suggested_specifics_json,
                        success=1 if success else 0,
                    )
                    if success:
                        changes_applied.append("specifics")
                    else:
                        errors.append("specifics update failed")
                except Exception as e:
                    await record_change(
                        session,
                        sku=sku,
                        field_changed="specifics",
                        old_value=listing.item_specifics_json,
                        new_value=opt.suggested_specifics_json,
                        success=0,
                        error_message=str(e),
                    )
                    errors.append(f"specifics: {e}")

        if changes_applied:
            await update_optimization_status(session, opt.id, "applied")

        return {
            "sku": sku,
            "applied": changes_applied,
            "errors": errors,
        }


@router.get("/history")
async def get_history(sku: Optional[str] = None, limit: int = 50):
    """変更履歴を返す"""
    async with AsyncSessionLocal() as session:
        history = await get_change_history(session, sku=sku, limit=limit)
        return {
            "history": [
                {
                    "id": h.id,
                    "sku": h.sku,
                    "field_changed": h.field_changed,
                    "old_value": h.old_value[:100],
                    "new_value": h.new_value[:100],
                    "applied_at": h.applied_at.isoformat(),
                    "success": bool(h.success),
                    "error_message": h.error_message,
                }
                for h in history
            ]
        }
