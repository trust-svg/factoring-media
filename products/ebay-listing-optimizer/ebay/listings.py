"""eBay Sell Inventory API からアクティブ出品を取得"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

import requests

from config import EBAY_API_BASE, EBAY_API_CALLS_PER_SECOND, EBAY_PAGE_SIZE
from ebay.auth import get_auth_headers

logger = logging.getLogger(__name__)


async def fetch_all_active_listings() -> list[dict]:
    """
    eBay Sell Inventory API で全アクティブ出品を取得する。
    ページネーション対応。各出品のオファー情報も取得してマージする。
    """
    headers = get_auth_headers()
    items = []
    offset = 0
    delay = 1.0 / EBAY_API_CALLS_PER_SECOND

    while True:
        url = f"{EBAY_API_BASE}/sell/inventory/v1/inventory_item"
        params = {"limit": EBAY_PAGE_SIZE, "offset": offset}
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        inventory_items = data.get("inventoryItems", [])
        if not inventory_items:
            break

        for item in inventory_items:
            sku = item.get("sku", "")
            product = item.get("product", {})
            availability = item.get("availability", {})
            quantity = (
                availability.get("shipToLocationAvailability", {})
                .get("quantity", 0)
            )

            # 画像URL
            image_urls = product.get("imageUrls", [])

            # Item Specifics
            aspects = product.get("aspects", {})

            items.append({
                "sku": sku,
                "title": product.get("title", sku),
                "description": product.get("description", ""),
                "quantity": quantity,
                "image_urls_json": json.dumps(image_urls),
                "item_specifics_json": json.dumps(aspects, ensure_ascii=False),
                "condition": item.get("condition", ""),
                "fetched_at": datetime.utcnow(),
            })

        total = data.get("total", 0)
        offset += EBAY_PAGE_SIZE
        if offset >= total:
            break

        await asyncio.sleep(delay)

    # オファー情報を取得して価格・カテゴリ・listing_id・offer_idをマージ
    offers_map = await _fetch_all_offers(headers, delay)
    for item in items:
        offer = offers_map.get(item["sku"])
        if offer:
            item["price_usd"] = offer.get("price_usd", 0.0)
            item["category_id"] = offer.get("category_id", "")
            item["category_name"] = offer.get("category_name", "")
            item["listing_id"] = offer.get("listing_id", "")
            item["offer_id"] = offer.get("offer_id", "")
        else:
            item.setdefault("price_usd", 0.0)
            item.setdefault("category_id", "")
            item.setdefault("category_name", "")
            item.setdefault("listing_id", "")
            item.setdefault("offer_id", "")

    logger.info(f"eBayから {len(items)} 件の出品を取得しました")
    return items


async def _fetch_all_offers(headers: dict, delay: float) -> dict[str, dict]:
    """全オファーを取得してSKUごとにマッピングする"""
    offers_map: dict[str, dict] = {}
    offset = 0

    while True:
        url = f"{EBAY_API_BASE}/sell/inventory/v1/offer"
        params = {"limit": EBAY_PAGE_SIZE, "offset": offset}
        resp = requests.get(url, headers=headers, params=params, timeout=30)

        if resp.status_code != 200:
            logger.warning(f"オファー取得失敗: {resp.status_code}")
            break

        data = resp.json()
        offers = data.get("offers", [])
        if not offers:
            break

        for offer in offers:
            sku = offer.get("sku", "")
            price_data = offer.get("pricingSummary", {}).get("price", {})
            category_id = offer.get("categoryId", "")
            listing_id = offer.get("listing", {}).get("listingId", "")
            offer_id = offer.get("offerId", "")

            offers_map[sku] = {
                "price_usd": float(price_data.get("value", 0.0)),
                "category_id": category_id,
                "category_name": "",  # カテゴリ名はAPIから別途取得が必要
                "listing_id": listing_id,
                "offer_id": offer_id,
            }

        total = data.get("total", 0)
        offset += EBAY_PAGE_SIZE
        if offset >= total:
            break

        await asyncio.sleep(delay)

    return offers_map
