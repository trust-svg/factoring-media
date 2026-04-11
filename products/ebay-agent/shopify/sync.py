"""Shopify 双方向同期ロジック

- push_listing_to_shopify: 1件をShopifyに同期
- push_all_unsynced: 未同期の全出品を一括同期
- close_shopify_for_sold_items: eBayで売れた商品をShopifyから削除
- get_shopify_price: eBay価格 → Shopify割引価格
- get_discount_rate: 現在の割引率をDB/configから取得
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from config import SHOPIFY_DISCOUNT_RATE
from database.models import get_db, Listing, ShopifyConfig
from shopify.client import ShopifyClient

logger = logging.getLogger("shopify.sync")


def get_discount_rate(db: Session) -> float:
    """割引率をShopifyConfigテーブルから取得。なければenv変数のデフォルト値。"""
    config = db.query(ShopifyConfig).filter_by(key="discount_rate").first()
    if config:
        return float(config.value)
    return SHOPIFY_DISCOUNT_RATE


def get_shopify_price(ebay_price_usd: float, discount_rate: float) -> float:
    """eBay価格に割引率を適用して2桁に丸める"""
    return round(ebay_price_usd * (1 - discount_rate), 2)


async def push_listing_to_shopify(sku: str) -> None:
    """1件のeBay出品をShopifyに同期する（すでに同期済みならスキップ）"""
    client = ShopifyClient()
    db = get_db()
    try:
        listing = db.query(Listing).filter_by(sku=sku).first()
        if not listing:
            logger.warning(f"SKU {sku} not found in DB")
            return
        if listing.shopify_product_id:
            logger.debug(f"SKU {sku} already synced to Shopify")
            return

        discount_rate = get_discount_rate(db)
        shopify_price = get_shopify_price(listing.price_usd, discount_rate)
        image_urls = json.loads(listing.image_urls_json or "[]")

        product_id, variant_id = await client.create_product(
            sku=listing.sku,
            title=listing.title,
            description_html=listing.description or "",
            price_usd=shopify_price,
            image_urls=image_urls,
        )

        listing.shopify_product_id = product_id
        listing.shopify_variant_id = variant_id
        listing.shopify_synced_at = datetime.utcnow()
        db.commit()
        logger.info(f"Pushed {sku} to Shopify (product_id={product_id})")

    except Exception:
        db.rollback()
        logger.exception(f"Failed to push {sku} to Shopify")
    finally:
        db.close()


async def push_all_unsynced() -> dict[str, int]:
    """shopify_product_idがNullで在庫>0の全ListingをShopifyに同期する"""
    db = get_db()
    try:
        listings = (
            db.query(Listing)
            .filter(Listing.shopify_product_id.is_(None), Listing.quantity > 0)
            .all()
        )
        skus = [l.sku for l in listings]
    finally:
        db.close()

    success, failed = 0, 0
    for sku in skus:
        try:
            await push_listing_to_shopify(sku)
            success += 1
        except Exception:
            failed += 1
            logger.exception(f"push_all_unsynced: failed for {sku}")

    logger.info(f"push_all_unsynced: success={success}, failed={failed}")
    return {"success": success, "failed": failed}


async def close_shopify_for_sold_items() -> int:
    """eBayで売れた（quantity=0）商品をShopifyから削除する"""
    client = ShopifyClient()
    db = get_db()
    try:
        sold = (
            db.query(Listing)
            .filter(Listing.quantity == 0, Listing.shopify_product_id.isnot(None))
            .all()
        )
        count = 0
        for listing in sold:
            try:
                await client.delete_product(listing.shopify_product_id)
                listing.shopify_product_id = None
                listing.shopify_variant_id = None
                db.commit()
                count += 1
                logger.info(f"Closed Shopify product for sold SKU {listing.sku}")
            except Exception:
                logger.exception(f"Failed to close Shopify for {listing.sku}")
        return count
    finally:
        db.close()
