"""DropshipCandidate を eBay ドラフト + eShip 在庫 に同時出品する。

UI/Telegram からのワンクリック承認で呼ばれる。

フロー:
  1. DropshipCandidate を pending 状態でロード
  2. listing/generator.generate_listing で AI タイトル/説明/Item Specifics 生成
  3. eShip create_eship_item で在庫登録（仕入元URL紐付け）
  4. eBay create_inventory_item + create_offer でドラフト作成
  5. DropshipCandidate.status = listed, listed_sku, listed_at を更新

publish_offer (eBay公開) は本パイプラインでは実行しない。
ドラフト確認後、別途 /api/dropship/candidates/{id}/publish で公開する。
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from comms.eship_client import create_eship_item
from database.models import DropshipCandidate, HotExpensiveItem
from ebay_core.client import (
    create_inventory_item,
    create_offer,
    get_fulfillment_policies,
    get_payment_policies,
    get_return_policies,
    publish_offer,
)
from listing.generator import generate_listing

logger = logging.getLogger(__name__)


def _ebay_condition_from_jp(jp_condition: str) -> str:
    """JPコンディション → eBay condition enum."""
    cl = (jp_condition or "").lower()
    if "新品" in jp_condition or "未使用" in jp_condition or "new" in cl:
        return "NEW"
    if "美品" in jp_condition:
        return "USED_EXCELLENT"
    if "良品" in jp_condition or "動作" in jp_condition:
        return "USED_VERY_GOOD"
    if "ジャンク" in jp_condition or "junk" in cl:
        return "FOR_PARTS_OR_NOT_WORKING"
    return "USED_GOOD"


async def publish_dropship_candidate(
    db: Session,
    candidate_id: int,
    publish_immediately: bool = False,
) -> dict:
    """候補ID 1件を eBay ドラフト + eShip に同時登録。

    Args:
        publish_immediately: True の場合、eBay で即公開（false=ドラフトのみ）。
    Returns:
        {"status": "ok"|"error", ...}
    """
    cand = db.get(DropshipCandidate, candidate_id)
    if not cand:
        return {"status": "error", "message": f"候補ID {candidate_id} が見つかりません"}
    if cand.status not in ("pending", "approved"):
        return {
            "status": "error",
            "message": f"候補#{candidate_id} は status={cand.status} のため出品不可",
        }

    hot = db.get(HotExpensiveItem, cand.hot_item_id) if cand.hot_item_id else None

    # 1) AI listing 生成
    try:
        listing_data = await generate_listing(
            product_name=hot.query if hot and hot.query else cand.jp_title,
            category=hot.category if hot and hot.category else "",
            condition=_ebay_condition_from_jp(cand.jp_condition),
        )
    except Exception as e:
        logger.exception("generate_listing 失敗 cand=%d", candidate_id)
        return {"status": "error", "message": f"AI生成失敗: {e}"}

    titles = listing_data.get("titles") or []
    if titles:
        first = titles[0]
        title = first.get("title", "") if isinstance(first, dict) else str(first)
    else:
        title = (cand.jp_title or "Item")[:80]
    if not title:
        title = (cand.jp_title or "Item")[:80]
    description = listing_data.get("description_html", "")
    raw_specs = listing_data.get("specs", {}) or {}
    aspects = {k: ([v] if isinstance(v, str) else v) for k, v in raw_specs.items() if v}
    category_id = (
        listing_data.get("category_id")
        or (hot.category_id if hot else "")
        or "625"  # fallback: Cameras
    )
    image_url = cand.jp_image_url or (hot.image_url if hot else "")

    sku = f"DS-{str(uuid.uuid4())[:6].upper()}"
    ebay_condition = _ebay_condition_from_jp(cand.jp_condition)
    price_usd = float(cand.ebay_target_price_usd or 0)

    # 2) eShip 登録
    eship_result = await create_eship_item(
        title=title,
        supplier_url=cand.jp_url,
        purchase_price=int(cand.jp_price_jpy or 0),
        platform=cand.jp_platform,
        selling_price_usd=price_usd,
        sku=sku,
        condition=ebay_condition,
        condition_description=cand.jp_condition or "",
        image_url=image_url,
        category_id=str(category_id),
        memo=(cand.jp_title or "")[:200],
    )
    eship_ok = eship_result.get("status") == "ok"
    eship_inv_id = eship_result.get("inventory_id", "")

    # 3) eBay Inventory + Offer (ドラフト)
    ebay_ok = False
    offer_id = ""
    listing_id = ""
    ebay_error = ""

    try:
        inv_result = create_inventory_item(
            sku=sku,
            product={
                "title": title,
                "description": description,
                "aspects": aspects,
                "imageUrls": [image_url] if image_url else [],
            },
            condition=ebay_condition,
            quantity=1,
        )
        if not inv_result.get("success"):
            ebay_error = inv_result.get("error", "inventory失敗")
        else:
            ff = get_fulfillment_policies()
            rp = get_return_policies()
            pp = get_payment_policies()
            offer_result = create_offer(
                sku=sku,
                category_id=str(category_id),
                price_usd=price_usd,
                condition=ebay_condition,
                fulfillment_policy_id=ff[0]["id"] if ff else "",
                return_policy_id=rp[0]["id"] if rp else "",
                payment_policy_id=pp[0]["id"] if pp else "",
                listing_description=description,
            )
            if offer_result.get("success"):
                offer_id = offer_result.get("offer_id", "")
                ebay_ok = True
                if publish_immediately and offer_id:
                    pub = publish_offer(offer_id)
                    if pub.get("success"):
                        listing_id = pub.get("listing_id", "")
                    else:
                        ebay_error = f"publish失敗: {pub.get('error', 'unknown')}"
            else:
                ebay_error = offer_result.get("error", "offer失敗")
    except Exception as e:
        logger.exception("eBay create 失敗 cand=%d", candidate_id)
        ebay_error = str(e)

    # 4) DB 更新
    cand.listed_sku = sku
    cand.approved_at = datetime.utcnow()
    if ebay_ok:
        cand.listed_at = datetime.utcnow()
        cand.status = "listed"
    else:
        cand.status = "approved"  # eShip だけ通った場合のリトライ余地を残す
    db.commit()

    return {
        "status": "ok" if (ebay_ok and eship_ok) else "partial",
        "candidate_id": cand.id,
        "sku": sku,
        "title": title,
        "price_usd": price_usd,
        "eship": {
            "ok": eship_ok,
            "inventory_id": eship_inv_id,
            "message": eship_result.get("message", ""),
        },
        "ebay": {
            "ok": ebay_ok,
            "offer_id": offer_id,
            "listing_id": listing_id,
            "error": ebay_error,
        },
        "category_id": category_id,
        "specs_count": len(aspects),
    }
