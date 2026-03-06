"""競合価格モニター

eBay Browse API で競合出品の価格を定期取得し、PriceHistory テーブルに蓄積する。
スケジューラーから呼ばれるバッチ処理。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime

from config import EBAY_FEE_RATE, PRICE_CHECK_INTERVAL_HOURS
from database.models import get_db
from database import crud
from ebay_core.client import search_ebay
from ebay_core.exchange_rate import get_usd_to_jpy

logger = logging.getLogger(__name__)

# API レート制限用
_DELAY_BETWEEN_CHECKS = 1.5  # 秒


def check_prices_for_listing(sku: str, title: str, our_price: float) -> dict | None:
    """1出品の競合価格をチェックし DB に記録"""
    # タイトルからブランド+モデル部分を抽出（先頭40文字程度で検索）
    search_query = title[:60] if len(title) > 60 else title

    competitors = search_ebay(search_query, limit=30)
    if not competitors:
        return None

    prices = [c["price"] for c in competitors if c["price"] > 0]
    if not prices:
        return None

    avg_price = sum(prices) / len(prices)
    min_price = min(prices)
    max_price = max(prices)
    rate = get_usd_to_jpy()

    db = get_db()
    try:
        crud.add_price_history(
            db,
            sku=sku,
            our_price_usd=our_price,
            avg_competitor_price_usd=round(avg_price, 2),
            lowest_competitor_price_usd=round(min_price, 2),
            num_competitors=len(prices),
            exchange_rate=rate,
        )
    finally:
        db.close()

    diff_pct = ((our_price - avg_price) / avg_price * 100) if avg_price else 0

    return {
        "sku": sku,
        "our_price": our_price,
        "avg_competitor": round(avg_price, 2),
        "min_competitor": round(min_price, 2),
        "max_competitor": round(max_price, 2),
        "diff_pct": round(diff_pct, 1),
        "num_competitors": len(prices),
        "needs_attention": abs(diff_pct) > 10,
    }


def run_price_monitor(limit: int = 50) -> dict:
    """
    全アクティブ出品の競合価格を一括チェック。
    Browse API レート制限のため上位 N 件のみ。

    Returns:
        {
            "checked": int,
            "alerts": list[dict],  # 価格差10%超のアイテム
            "skipped": int,
            "errors": int,
        }
    """
    db = get_db()
    try:
        listings = crud.get_all_listings(db)
    finally:
        db.close()

    if not listings:
        return {"checked": 0, "alerts": [], "skipped": 0, "errors": 0}

    # 価格が高い順にチェック（高額商品の価格ズレが影響大）
    listings_sorted = sorted(listings, key=lambda l: l.price_usd, reverse=True)
    target = listings_sorted[:limit]

    results = []
    alerts = []
    errors = 0

    for listing in target:
        try:
            result = check_prices_for_listing(
                sku=listing.sku,
                title=listing.title,
                our_price=listing.price_usd,
            )
            if result:
                results.append(result)
                if result["needs_attention"]:
                    alerts.append(result)
            time.sleep(_DELAY_BETWEEN_CHECKS)
        except Exception as e:
            logger.warning(f"Price check failed for {listing.sku}: {e}")
            errors += 1

    logger.info(
        f"Price monitor: {len(results)} checked, "
        f"{len(alerts)} alerts, {errors} errors"
    )

    return {
        "checked": len(results),
        "alerts": alerts,
        "skipped": len(listings) - len(target),
        "errors": errors,
        "timestamp": datetime.utcnow().isoformat(),
    }
