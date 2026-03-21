"""テンプレート変数解決 — 注文/商品/追跡データから変数を展開"""
from __future__ import annotations

import logging
import re
from typing import Dict, Optional

from sqlalchemy.orm import Session

from database.models import SalesRecord, Listing, InventoryItem

logger = logging.getLogger(__name__)

# キャリア追跡URL
CARRIER_TRACKING_URLS = {
    "DHL": "https://www.dhl.com/en/express/tracking.html?AWB={tracking}",
    "FedEx": "https://www.fedex.com/fedextrack/?trknbr={tracking}",
    "SpeedPAK": "https://www.orangeconnex.com/tracking?language=en&trackingnumber={tracking}",
    "Japan Post": "https://trackings.post.japanpost.jp/services/srv/search/?requestNo1={tracking}&locale=en",
    "UPS": "https://www.ups.com/track?tracknum={tracking}",
    "EMS": "https://trackings.post.japanpost.jp/services/srv/search/?requestNo1={tracking}&locale=en",
}


def resolve_variables(
    template_body: str,
    db: Session,
    buyer_username: str = "",
    item_id: str = "",
    order_id: str = "",
    event_data: Optional[Dict] = None,
) -> str:
    """テンプレート内の {variable} を実データで置換する。

    対応変数:
        {buyer_name}, {item_title}, {item_id}, {order_id},
        {tracking_number}, {tracking_url}, {edd},
        {price}, {carrier}, {sku}, {marketplace}
    """
    if not template_body:
        return ""

    data = event_data or {}
    vars_map: Dict[str, str] = {
        "buyer_name": buyer_username or data.get("buyer_name", ""),
        "item_id": item_id or data.get("item_id", ""),
        "order_id": order_id or data.get("order_id", ""),
    }

    # SalesRecord からデータ取得
    sale = None
    if order_id:
        sale = db.query(SalesRecord).filter(SalesRecord.order_id == order_id).first()
    elif item_id and buyer_username:
        sale = db.query(SalesRecord).filter(
            SalesRecord.item_id == item_id,
            SalesRecord.buyer_name == buyer_username,
        ).order_by(SalesRecord.sold_at.desc()).first()

    if sale:
        vars_map.update({
            "item_title": sale.title or "",
            "tracking_number": sale.tracking_number or "",
            "carrier": sale.shipping_method or "",
            "price": f"${sale.sale_price_usd:.2f}" if sale.sale_price_usd else "",
            "sku": sale.sku or "",
            "marketplace": sale.marketplace or "US",
            "order_id": sale.order_id or vars_map["order_id"],
            "buyer_name": sale.buyer_name or vars_map["buyer_name"],
        })

        # EDD (Estimated Delivery Date)
        if sale.ship_by_date:
            from datetime import timedelta
            edd = sale.ship_by_date + timedelta(days=10)
            vars_map["edd"] = edd.strftime("%B %d, %Y")
        else:
            vars_map["edd"] = "7-14 business days"

        # 追跡URL
        tracking_url = _get_tracking_url(
            sale.tracking_number or "",
            sale.shipping_method or "",
        )
        vars_map["tracking_url"] = tracking_url or ""
    else:
        # SalesRecord がない場合のフォールバック
        # Listing テーブルから商品名取得
        if item_id:
            listing = db.query(Listing).filter(Listing.listing_id == item_id).first()
            if listing:
                vars_map["item_title"] = listing.title or ""
                vars_map["sku"] = listing.sku or ""
                vars_map["price"] = f"${listing.price_usd:.2f}" if listing.price_usd else ""

        vars_map.setdefault("item_title", data.get("item_title", ""))
        vars_map.setdefault("tracking_number", "")
        vars_map.setdefault("tracking_url", "")
        vars_map.setdefault("carrier", "")
        vars_map.setdefault("price", data.get("price", ""))
        vars_map.setdefault("sku", "")
        vars_map.setdefault("edd", "7-14 business days")
        vars_map.setdefault("marketplace", "US")

    # イベントデータで上書き（あれば）
    for key in ("buyer_name", "item_title", "tracking_number", "price"):
        if data.get(key):
            vars_map[key] = data[key]

    # 変数置換
    result = template_body
    for var_name, var_value in vars_map.items():
        result = result.replace(f"{{{var_name}}}", str(var_value))

    # 未解決変数をクリーンアップ
    result = re.sub(r"\{[a-z_]+\}", "", result)

    return result.strip()


def _get_tracking_url(tracking_number: str, shipping_method: str) -> str:
    """追跡番号とキャリアから追跡URLを生成する。"""
    if not tracking_number:
        return ""

    method = shipping_method.lower() if shipping_method else ""

    # キャリア名から判定
    for carrier, url_template in CARRIER_TRACKING_URLS.items():
        if carrier.lower() in method:
            return url_template.replace("{tracking}", tracking_number)

    # 追跡番号パターンから自動判定
    num = tracking_number.strip()
    if re.match(r"^\d{10}$", num):
        return CARRIER_TRACKING_URLS["DHL"].replace("{tracking}", num)
    if re.match(r"^\d{12,15}$", num):
        return CARRIER_TRACKING_URLS["FedEx"].replace("{tracking}", num)
    if re.match(r"^1Z", num):
        return CARRIER_TRACKING_URLS["UPS"].replace("{tracking}", num)
    if re.match(r"^E[A-Z]\d{9}JP$", num) or re.match(r"^\d{13}$", num):
        return CARRIER_TRACKING_URLS["Japan Post"].replace("{tracking}", num)
    if "speedpak" in method or "orangeconnex" in method or "speed pak" in method:
        return CARRIER_TRACKING_URLS["SpeedPAK"].replace("{tracking}", num)

    return ""
