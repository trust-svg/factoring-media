"""定期実行ジョブ — APScheduler CronTrigger 用"""
from __future__ import annotations

import logging
from datetime import datetime

from database.models import get_db
from database import crud
from comms.line_notify import send_line_message

logger = logging.getLogger(__name__)


def send_morning_digest():
    """朝のダイジェスト — 出品数・売上・在庫切れ・為替"""
    logger.info("Running morning digest...")
    db = get_db()
    try:
        stats = crud.get_dashboard_stats(db)

        # 為替レート取得
        try:
            import requests
            resp = requests.get(
                "https://api.exchangerate-api.com/v4/latest/USD", timeout=5
            )
            rate = resp.json().get("rates", {}).get("JPY", 0)
        except Exception:
            rate = 0

        lines = [
            f"☀️ eBay Agent — Morning Digest",
            f"📅 {datetime.now().strftime('%Y/%m/%d %H:%M')}",
            "",
            f"📦 Total Listings: {stats.get('total_listings', 0)}",
            f"✅ In Stock: {stats.get('in_stock', 0)}",
            f"❌ Out of Stock: {stats.get('out_of_stock', 0)}",
            f"🔍 Source Candidates: {stats.get('source_candidates', 0)}",
            f"📋 Pending Procurement: {stats.get('pending_procurements', 0)}",
        ]
        if rate:
            lines.append(f"💱 USD/JPY: ¥{rate:.1f}")

        # 30日売上
        summary = crud.get_sales_summary(db, days=30)
        if summary.get("total_revenue"):
            lines.extend([
                "",
                f"💰 30d Revenue: ${summary['total_revenue']:.2f}",
                f"📊 30d Orders: {summary.get('total_orders', 0)}",
            ])

        text = "\n".join(lines)
        send_line_message(text)
        logger.info("Morning digest sent")
    except Exception as e:
        logger.exception(f"Morning digest failed: {e}")
    finally:
        db.close()


def send_weekly_report():
    """週間レポート — 週間売上・利益・トップ商品"""
    logger.info("Running weekly report...")
    db = get_db()
    try:
        summary = crud.get_sales_summary(db, days=7)
        stats = crud.get_dashboard_stats(db)

        lines = [
            f"📊 eBay Agent — Weekly Report",
            f"📅 Week of {datetime.now().strftime('%Y/%m/%d')}",
            "",
            f"💰 Revenue: ${summary.get('total_revenue', 0):.2f}",
            f"📦 Orders: {summary.get('total_orders', 0)}",
            f"📈 Avg Order: ${summary.get('avg_order_value', 0):.2f}",
            "",
            f"📋 Active Listings: {stats.get('total_listings', 0)}",
            f"❌ Out of Stock: {stats.get('out_of_stock', 0)}",
            f"🛒 Procurement Cost: ¥{stats.get('total_procurement_cost_jpy', 0):,}",
        ]

        # トップ商品
        top = summary.get("top_items", [])
        if top:
            lines.append("")
            lines.append("🏆 Top Items:")
            for i, item in enumerate(top[:5], 1):
                lines.append(f"  {i}. {item.get('title', '?')[:30]} — ${item.get('revenue', 0):.2f}")

        text = "\n".join(lines)
        send_line_message(text)
        logger.info("Weekly report sent")
    except Exception as e:
        logger.exception(f"Weekly report failed: {e}")
    finally:
        db.close()


def auto_sync_sales():
    """売上データ自動同期"""
    logger.info("Running auto sales sync...")
    try:
        from comms.sales_analytics import sync_ebay_sales
        db = get_db()
        try:
            result = sync_ebay_sales(db, days=3)
            logger.info(f"Auto sync: {result.get('synced', 0)} orders synced")

            # 新しい注文があればLINE通知
            synced = result.get("synced", 0)
            if synced > 0:
                send_line_message(f"🔄 eBay売上同期完了: {synced}件の新規注文")
        finally:
            db.close()
    except Exception as e:
        logger.exception(f"Auto sales sync failed: {e}")
