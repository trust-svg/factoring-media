"""URL-to-Listing Pipeline — input a source URL, auto-create eBay listing + eShip entry.

Flow:
1. scrape_detail(url) → detailed item data
2. run_agent_team() → research, quality, pricing, listing
3. update_eship_item() → eShip registration
4. create_inventory_item() + create_offer() → eBay draft
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

import aiosqlite

import config as dw_config
from scrapers.detail import scrape_detail, detect_platform
from agents import run_agent_team

logger = logging.getLogger(__name__)


async def url_to_listing(
    url: str,
    min_profit_jpy: int = 0,
    min_margin: float = 0,
) -> dict:
    """Full pipeline: URL → scrape → agents → eShip → eBay draft.

    Returns: {"status": "ok", ...} or {"status": "error", "message": ...}
    """
    # Step 1: Scrape source listing
    logger.info(f"URL-to-Listing: scraping {url}")
    detail = await scrape_detail(url)
    if not detail:
        return {"status": "error", "message": f"URLのスクレイピングに失敗: {url}"}

    if detail.price <= 0:
        return {"status": "error", "message": "価格を取得できませんでした"}

    product_name = detail.title
    logger.info(f"Scraped: {product_name} ¥{detail.price:,} ({len(detail.image_urls)} images)")

    # Step 2: Run agent team
    try:
        team_result = await run_agent_team(
            product_name=product_name,
            purchase_price_jpy=detail.price,
            condition=detail.condition,
            description_jp=detail.description,
            image_urls=detail.image_urls,
            min_profit_jpy=min_profit_jpy,
            min_margin=min_margin,
        )
    except Exception as e:
        logger.error(f"Agent team error: {e}")
        return {"status": "error", "message": f"AI分析エラー: {e}"}

    listing_data = team_result["listing"]
    pricing = team_result["pricing"]
    quality = team_result["quality"]
    research = team_result["research"]

    title = listing_data.get("title", product_name[:80])
    description = listing_data.get("description_html", "")
    specs = listing_data.get("specs", {})
    category_id = listing_data.get("category_id", "")
    ebay_condition = quality.get("ebay_condition", "USED_VERY_GOOD")
    price_usd = pricing.get("price_usd", 0)

    # Step 3: Register on eShip (new item)
    eship_ok = False
    try:
        from eship import create_eship_item
        eship_result = await create_eship_item(
            title=title,
            supplier_url=url,
            purchase_price=detail.price,
            platform=detail.platform,
            selling_price_usd=price_usd,
            sku=sku,
            condition=ebay_condition,
            condition_description=quality.get("condition_notes_en", ""),
            image_url=detail.image_urls[0] if detail.image_urls else "",
            category_id=category_id,
            memo=detail.title[:200],  # 元の日本語タイトル
        )
        eship_ok = eship_result.get("status") == "ok"
        logger.info(f"eShip: {'OK' if eship_ok else 'FAILED'} - {eship_result.get('message', '')}")
    except Exception as e:
        logger.error(f"eShip registration error: {e}")

    # Step 4: Create eBay draft listing
    sku = f"UTL-{str(uuid.uuid4())[:6].upper()}"
    offer_id = ""
    ebay_ok = False

    try:
        from discovery import _import_ebay_client
        _import_ebay_client()  # ensure ebay modules loadable
        from ebay_core.client import create_inventory_item, create_offer

        # Use source images
        image_urls = detail.image_urls[:12]  # eBay max 12

        inv_result = create_inventory_item(
            sku=sku,
            product={
                "title": title,
                "description": description,
                "aspects": specs,
                "imageUrls": image_urls,
            },
            condition=ebay_condition,
            quantity=1,
        )
        logger.info(f"Inventory item: {inv_result}")

        offer_result = create_offer(
            sku=sku,
            category_id=category_id,
            price_usd=price_usd,
            condition=ebay_condition,
            listing_description=description,
        )
        offer_id = offer_result.get("offer_id", "")
        ebay_ok = offer_result.get("success", False)
        logger.info(f"Offer: {offer_result}")

    except Exception as e:
        logger.error(f"eBay listing creation error: {e}")

    # Step 5: Save to DB
    try:
        async with aiosqlite.connect(dw_config.DATABASE_PATH) as db:
            await db.execute("""
                INSERT INTO discovery_candidates
                (id, demand_item_id, source_platform, source_title, source_price,
                 source_url, source_image_url, source_condition,
                 ebay_est_price_usd, est_profit_jpy, brand, model,
                 status, eship_registered, ebay_listing_id)
                VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sku, detail.platform, detail.title, detail.price,
                url, detail.image_urls[0] if detail.image_urls else "",
                detail.condition, price_usd, pricing.get("profit_jpy", 0),
                specs.get("Brand", ""), specs.get("Model", ""),
                "listed" if ebay_ok else "draft",
                1 if eship_ok else 0, offer_id,
            ))
            await db.commit()
    except Exception as e:
        logger.error(f"DB save error: {e}")

    return {
        "status": "ok",
        "sku": sku,
        "title": title,
        "price_usd": price_usd,
        "profit_jpy": pricing.get("profit_jpy", 0),
        "margin": pricing.get("margin", 0),
        "offer_id": offer_id,
        "eship_registered": eship_ok,
        "ebay_created": ebay_ok,
        "category_id": category_id,
        "condition": ebay_condition,
        "image_count": len(detail.image_urls),
        "specs_count": len(specs),
    }
