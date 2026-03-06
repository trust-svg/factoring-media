"""売上分析モジュール

eBay Trading API から注文データを取得し、
利益・カテゴリ別パフォーマンス・トレンドを分析する。
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime

from config import EBAY_FEE_RATE
from database.models import get_db
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
                total_cost_jpy = source_cost + shipping_cost

                profit = sale_price - ebay_fees - (total_cost_jpy / rate if total_cost_jpy else 0)

                crud.add_sales_record(
                    db,
                    sku=sku,
                    title=item["title"],
                    sale_price_usd=sale_price,
                    source_cost_jpy=source_cost,
                    shipping_cost_jpy=shipping_cost,
                    ebay_fees_usd=round(ebay_fees, 2),
                    exchange_rate=rate,
                    profit_usd=round(profit, 2),
                )
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
            daily[day_key]["profit"] += r.profit_usd
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
            sku_totals[r.sku]["profit"] += r.profit_usd
            sku_totals[r.sku]["count"] += 1

        top_products = sorted(
            [
                {
                    "sku": sku,
                    "title": data["title"][:60],
                    "revenue_usd": round(data["revenue"], 2),
                    "profit_usd": round(data["profit"], 2),
                    "sales_count": data["count"],
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
