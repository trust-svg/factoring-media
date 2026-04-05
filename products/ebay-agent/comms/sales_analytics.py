"""売上分析モジュール

eBay Trading API から注文データを取得し、
利益・カテゴリ別パフォーマンス・トレンドを分析する。
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime

from config import EBAY_FEE_RATE, PAYONEER_FEE_RATE
from database.models import InventoryItem, Listing, get_db
from database import crud
from ebay_core.client import get_recent_orders
from ebay_core.exchange_rate import get_usd_to_jpy

logger = logging.getLogger(__name__)


def sync_sales_data(days: int = 30) -> dict:
    """
    eBay API から注文データを取得し DB に同期する。

    Returns:
        {
            "orders_fetched": int,
            "new_sales_recorded": int,
            "total_revenue_usd": float,
        }
    """
    orders = get_recent_orders(days=days)
    if not orders:
        return {
            "orders_fetched": 0,
            "new_sales_recorded": 0,
            "total_revenue_usd": 0,
        }

    rate = get_usd_to_jpy()
    db = get_db()
    new_count = 0

    try:
        for order in orders:
            for item in order["items"]:
                sku = item["sku"]
                sale_price = item["price_usd"]
                ebay_fees = sale_price * EBAY_FEE_RATE

                # 既存の売上レコードチェック（重複防止）
                existing = (
                    db.query(crud.SalesRecord)
                    .filter(
                        crud.SalesRecord.sku == sku,
                        crud.SalesRecord.sale_price_usd == sale_price,
                    )
                    .first()
                )
                if existing:
                    continue

                # 仕入れ価格を Procurement テーブルから取得
                source_cost, shipping_cost = crud.get_latest_procurement_cost(db, sku)

                # Payoneer手数料 (2%)
                payoneer_fee = round(sale_price * PAYONEER_FEE_RATE, 2)

                # order_id・追跡番号・バイヤー情報取得
                order_id = order.get("order_id", "")
                tracking_number = order.get("tracking_number", "")
                shipping_carrier = order.get("shipping_carrier", "")
                buyer_name = order.get("buyer_name", "")
                buyer_country = order.get("buyer_country", "")
                created_time = order.get("created_time", "")

                # eBayのISO日時をdatetimeに変換
                sold_at = None
                if created_time:
                    try:
                        sold_at = datetime.strptime(
                            created_time.replace("Z", "+00:00")[:19],
                            "%Y-%m-%dT%H:%M:%S",
                        )
                    except ValueError:
                        pass

                # 有在庫アイテムからコスト取得（SKUマッチ）
                inv_item = (
                    db.query(InventoryItem)
                    .filter(
                        InventoryItem.sku == sku,
                        InventoryItem.status.in_(["in_stock", "listed"]),
                    )
                    .first()
                )
                # 有在庫の仕入原価を優先的に使用
                if inv_item and inv_item.purchase_price_jpy:
                    source_cost = inv_item.purchase_price_jpy + inv_item.consumption_tax_jpy

                sale_record = crud.add_sales_record(
                    db,
                    order_id=order_id,
                    item_id=item.get("item_id", ""),
                    sku=sku,
                    title=item["title"],
                    sale_price_usd=sale_price,
                    source_cost_jpy=source_cost,
                    shipping_cost_jpy=shipping_cost,
                    ebay_fees_usd=round(ebay_fees, 2),
                    payoneer_fee_usd=payoneer_fee,
                    exchange_rate=rate,
                    tracking_number=tracking_number,
                    shipping_method=shipping_carrier,
                    buyer_name=buyer_name,
                    buyer_country=buyer_country,
                    **({"sold_at": sold_at} if sold_at else {}),
                )

                # 有在庫ステータスを「売却済」に自動更新
                if inv_item:
                    inv_item.status = "sold"
                    inv_item.sold_at = sold_at or datetime.utcnow()
                    inv_item.sale_record_id = sale_record.id
                    db.commit()
                    logger.info(f"有在庫 #{inv_item.id} を売却済に更新 (SKU: {sku})")

                new_count += 1
    finally:
        db.close()

    total_revenue = sum(
        item["price_usd"]
        for order in orders
        for item in order["items"]
    )

    return {
        "orders_fetched": len(orders),
        "new_sales_recorded": new_count,
        "total_revenue_usd": round(total_revenue, 2),
    }


def get_sales_analytics(days: int = 30) -> dict:
    """
    包括的な売上分析データを返す。

    Returns:
        日次推移、カテゴリ別、トップ商品のデータ
    """
    db = get_db()
    try:
        # 基本サマリー
        summary = crud.get_sales_summary(db, days=days)

        # 全レコード取得
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)
        records = (
            db.query(crud.SalesRecord)
            .filter(crud.SalesRecord.sold_at >= cutoff)
            .all()
        )

        # 日次推移
        daily: dict[str, dict] = defaultdict(lambda: {"revenue": 0, "profit": 0, "count": 0})
        for r in records:
            day_key = r.sold_at.strftime("%Y-%m-%d")
            daily[day_key]["revenue"] += r.sale_price_usd
            daily[day_key]["profit"] += r.net_profit_usd
            daily[day_key]["count"] += 1

        daily_trend = [
            {
                "date": k,
                "revenue_usd": round(v["revenue"], 2),
                "profit_usd": round(v["profit"], 2),
                "sales_count": v["count"],
            }
            for k, v in sorted(daily.items())
        ]

        # トップ商品（売上額順）
        sku_totals: dict[str, dict] = defaultdict(
            lambda: {"title": "", "revenue": 0, "profit": 0, "count": 0}
        )
        for r in records:
            sku_totals[r.sku]["title"] = r.title
            sku_totals[r.sku]["revenue"] += r.sale_price_usd
            sku_totals[r.sku]["profit"] += r.net_profit_usd
            sku_totals[r.sku]["count"] += 1

        # SKU→画像URLマップ（Listingテーブルから一括取得）
        import json as _json
        skus = list(sku_totals.keys())
        image_map: dict[str, str] = {}
        if skus:
            listings = db.query(Listing.sku, Listing.image_urls_json).filter(Listing.sku.in_(skus)).all()
            for l in listings:
                try:
                    urls = _json.loads(l.image_urls_json) if l.image_urls_json else []
                    if urls:
                        image_map[l.sku] = urls[0]
                except (ValueError, IndexError):
                    pass

        top_products = sorted(
            [
                {
                    "sku": sku,
                    "title": data["title"][:60],
                    "revenue_usd": round(data["revenue"], 2),
                    "profit_usd": round(data["profit"], 2),
                    "sales_count": data["count"],
                    "image_url": image_map.get(sku, ""),
                }
                for sku, data in sku_totals.items()
            ],
            key=lambda x: x["revenue_usd"],
            reverse=True,
        )[:20]

        return {
            "period_days": days,
            "summary": summary,
            "daily_trend": daily_trend,
            "top_products": top_products,
            "total_unique_products_sold": len(sku_totals),
        }
    finally:
        db.close()
