"""バイヤー購入履歴 — 注文履歴・追跡番号・フィードバック統合"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from database.models import SalesRecord, BuyerMessage, Listing

logger = logging.getLogger(__name__)

# キャリア追跡URL（SpeedPAK含む）
CARRIER_TRACKING_URLS = {
    "DHL": "https://www.dhl.com/en/express/tracking.html?AWB={tracking}",
    "FedEx": "https://www.fedex.com/fedextrack/?trknbr={tracking}",
    "SpeedPAK": "https://www.orangeconnex.com/tracking?language=en&trackingnumber={tracking}",
    "Japan Post": "https://trackings.post.japanpost.jp/services/srv/search/?requestNo1={tracking}&locale=en",
    "UPS": "https://www.ups.com/track?tracknum={tracking}",
    "EMS": "https://trackings.post.japanpost.jp/services/srv/search/?requestNo1={tracking}&locale=en",
}


def get_buyer_full_history(db: Session, buyer_username: str) -> dict:
    """バイヤーの完全な購入履歴を取得する。

    Returns:
        {
            "buyer": str,
            "orders": [{注文情報 + 追跡 + トラブル + メッセージ数}],
            "stats": {合計注文数、金額、利益、トラブル数},
            "message_threads": [{item_id, message_count, last_date}],
        }
    """
    # SalesRecordを検索: buyer_name直接 OR item_id経由
    sales = db.query(SalesRecord).filter(
        SalesRecord.buyer_name == buyer_username
    ).order_by(SalesRecord.sold_at.desc()).all()
    if not sales:
        buyer_item_ids = [
            m.item_id for m in db.query(BuyerMessage.item_id).filter(
                BuyerMessage.sender == buyer_username,
                BuyerMessage.item_id != "",
            ).distinct().all()
        ]
        if buyer_item_ids:
            sales = db.query(SalesRecord).filter(
                SalesRecord.item_id.in_(buyer_item_ids)
            ).order_by(SalesRecord.sold_at.desc()).all()

    # メッセージスレッド
    messages = db.query(BuyerMessage).filter(
        (BuyerMessage.sender == buyer_username) | (BuyerMessage.recipient == buyer_username)
    ).all()

    # 注文ごとの情報を構築
    orders = []
    for s in sales:
        # 追跡番号 + キャリアリンク
        tracking_info = _build_tracking_info(s.tracking_number or "", s.shipping_method or "")
        logger.info(f"tracking_info for {s.item_id}: method={s.shipping_method} track={s.tracking_number} -> {tracking_info}")

        # この注文に関するメッセージ数
        order_messages = [m for m in messages if m.item_id == s.item_id]

        # トラブル判定
        trouble_type = _detect_trouble(s.progress)

        orders.append({
            "order_id": s.order_id,
            "item_id": s.item_id,
            "sku": s.sku,
            "title": s.title,
            "sale_price_usd": s.sale_price_usd,
            "source_cost_jpy": s.source_cost_jpy,
            "net_profit_usd": s.net_profit_usd,
            "net_profit_jpy": s.net_profit_jpy,
            "profit_margin_pct": s.profit_margin_pct,
            "shipping_method": s.shipping_method,
            "tracking_number": s.tracking_number or "",
            "tracking_url": tracking_info.get("url", ""),
            "carrier": tracking_info.get("carrier", ""),
            "progress": s.progress,
            "trouble_type": trouble_type,
            "trouble_icon": _trouble_icon(trouble_type),
            "message_count": len(order_messages),
            "buyer_country": s.buyer_country,
            "marketplace": s.marketplace,
            "sold_at": s.sold_at.isoformat() if s.sold_at else "",
            "ship_by_date": s.ship_by_date.isoformat() if s.ship_by_date else "",
        })

    # 統計
    total_revenue = sum(s.sale_price_usd for s in sales)
    total_profit = sum(s.net_profit_usd for s in sales)
    trouble_count = sum(1 for o in orders if o["trouble_type"])

    # メッセージスレッドサマリー
    thread_map: Dict[str, dict] = {}
    for m in messages:
        key = m.item_id or "general"
        if key not in thread_map:
            thread_map[key] = {"item_id": key, "message_count": 0, "last_date": ""}
        thread_map[key]["message_count"] += 1
        if m.received_at:
            date_str = m.received_at.isoformat()
            if date_str > thread_map[key]["last_date"]:
                thread_map[key]["last_date"] = date_str

    return {
        "buyer": buyer_username,
        "orders": orders,
        "stats": {
            "total_orders": len(sales),
            "total_revenue_usd": round(total_revenue, 2),
            "total_profit_usd": round(total_profit, 2),
            "avg_profit_margin": round(
                sum(s.profit_margin_pct for s in sales) / len(sales), 1
            ) if sales else 0,
            "trouble_count": trouble_count,
            "first_order": sales[-1].sold_at.isoformat() if sales else "",
            "last_order": sales[0].sold_at.isoformat() if sales else "",
        },
        "message_threads": sorted(
            thread_map.values(),
            key=lambda t: t["last_date"],
            reverse=True,
        ),
    }


def get_order_tracking(db: Session, order_id: str) -> dict:
    """特定注文の追跡情報を取得する。"""
    sale = db.query(SalesRecord).filter(SalesRecord.order_id == order_id).first()
    if not sale:
        return {"error": "Order not found"}

    tracking_info = _build_tracking_info(sale.tracking_number, sale.shipping_method)
    return {
        "order_id": sale.order_id,
        "tracking_number": sale.tracking_number or "",
        "carrier": tracking_info.get("carrier", ""),
        "tracking_url": tracking_info.get("url", ""),
        "shipping_method": sale.shipping_method,
        "progress": sale.progress,
        "ship_by_date": sale.ship_by_date.isoformat() if sale.ship_by_date else "",
    }


def edit_listing_from_chat(db: Session, item_id: str, updates: dict) -> dict:
    """チャット内から商品情報を編集する。

    updates: {"sku": str, "quantity": int, "price_usd": float}
    """
    from ebay_core.client import update_listing

    # item_id → SKU を解決
    listing = db.query(Listing).filter(Listing.listing_id == item_id).first()
    if not listing:
        return {"error": f"Listing not found for item {item_id}"}

    sku = listing.sku
    api_updates = {}

    if "price_usd" in updates:
        api_updates["price_usd"] = float(updates["price_usd"])
    if "quantity" in updates:
        api_updates["quantity"] = int(updates["quantity"])

    if api_updates:
        result = update_listing(sku, api_updates)
        if result.get("success"):
            # ローカルDBも更新
            if "price_usd" in api_updates:
                listing.price_usd = api_updates["price_usd"]
            if "quantity" in api_updates:
                listing.quantity = api_updates["quantity"]
            db.commit()
        return result

    # SKU（Custom Label）変更はReviseItemで
    if "sku" in updates and updates["sku"] != sku:
        return {"error": "SKU change requires ReviseItem API — not yet implemented"}

    return {"error": "No valid updates provided"}


# ── ヘルパー ─────────────────────────────────────────────

def _build_tracking_info(tracking_number: str, shipping_method: str) -> dict:
    """追跡番号からキャリアとURLを生成する。"""
    if not tracking_number:
        return {"carrier": "", "url": ""}

    carrier = _detect_carrier(tracking_number, shipping_method)
    url = ""
    if carrier and carrier in CARRIER_TRACKING_URLS:
        url = CARRIER_TRACKING_URLS[carrier].replace("{tracking}", tracking_number)

    return {"carrier": carrier, "url": url}


def _detect_carrier(tracking_number: str, shipping_method: str = "") -> str:
    """追跡番号パターンとキャリア名からキャリアを判定する。"""
    method = (shipping_method or "").lower()
    num = tracking_number.strip()

    # 名前ベース判定
    if "dhl" in method:
        return "DHL"
    if "fedex" in method:
        return "FedEx"
    if any(k in method for k in ("speedpak", "speed pak", "orangeconnex", "sppeedpak", "sppedpak")):
        return "SpeedPAK"
    if "ups" in method:
        return "UPS"
    if "ems" in method:
        return "EMS"
    if "japan post" in method or "jp post" in method:
        return "Japan Post"
    # eBay固有のshipping method名にSpeedPAKが隠れているケース
    if "expedited" in method and ("outside" in method or "international" in method):
        return "SpeedPAK"

    # パターンベース判定
    if re.match(r"^\d{10}$", num):
        return "DHL"
    if re.match(r"^\d{12,15}$", num):
        return "FedEx"
    if re.match(r"^1Z", num):
        return "UPS"
    if re.match(r"^E[A-Z]\d{9}JP$", num):
        return "EMS"
    if re.match(r"^\d{13}$", num):
        return "Japan Post"
    # SpeedPAK: EX/EM始まりの長い番号（OrangeConnex形式）
    if re.match(r"^E[MX]\d{10,}", num):
        return "SpeedPAK"

    return ""


def _detect_trouble(progress: str) -> str:
    """進捗ステータスからトラブルタイプを判定する。"""
    if not progress:
        return ""
    p = progress.lower()
    if p in ("キャンセル", "cancelled", "cancel"):
        return "cancel"
    if p in ("返金", "refunded", "refund"):
        return "refund"
    if p in ("返品", "returned", "return"):
        return "return"
    if p in ("dispute", "ディスプート"):
        return "dispute"
    return ""


def _trouble_icon(trouble_type: str) -> str:
    """トラブルタイプのアイコンを返す。"""
    icons = {
        "cancel": "❌",
        "refund": "💰",
        "return": "↩️",
        "dispute": "⚠️",
    }
    return icons.get(trouble_type, "")
