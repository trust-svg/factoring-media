"""統合eBay APIクライアント

ebay-inventory-tool と ebay-listing-optimizer の共通処理を統合。
- OAuth 2.0 トークン管理 (refresh_token フロー)
- Sell Inventory API (在庫・出品管理)
- Trading API (GetMyeBaySelling フォールバック)
- Browse API (公開情報取得・競合分析)
- Offer/Listing 更新
"""

from __future__ import annotations

import json
import logging
import os
import time
import xml.etree.ElementTree as ET
from base64 import b64encode
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from datetime import datetime, timedelta

import requests

# When running from deal-watcher, 'config' is deal-watcher's module (no EBAY_API_BASE).
# Use ebay_config.py as fallback.
try:
    from ebay_config import (
        EBAY_API_BASE,
        EBAY_CLIENT_ID,
        EBAY_CLIENT_SECRET,
        EBAY_PAGE_SIZE,
        EBAY_TOKEN_FILE,
    )
except ImportError:
    from config import (
        EBAY_API_BASE,
        EBAY_CLIENT_ID,
        EBAY_CLIENT_SECRET,
        EBAY_PAGE_SIZE,
        EBAY_TOKEN_FILE,
    )

logger = logging.getLogger(__name__)


# ── データモデル ──────────────────────────────────────────


@dataclass
class EbayItem:
    """eBay出品アイテム"""

    item_id: str
    sku: str
    title: str
    price_usd: float
    quantity: int
    is_out_of_stock: bool
    listing_id: str = ""
    category_id: str = ""
    category_name: str = ""
    condition: str = ""
    image_urls: list[str] = field(default_factory=list)
    item_specifics: dict = field(default_factory=dict)
    description: str = ""
    offer_id: str = ""


# ── トークン管理 ──────────────────────────────────────────


def _load_token() -> dict:
    """トークンをロード (環境変数 or ファイル)"""
    env_refresh = os.environ.get("EBAY_REFRESH_TOKEN")
    if env_refresh:
        return {"refresh_token": env_refresh, "expires_at": 0}
    if EBAY_TOKEN_FILE.exists():
        with open(EBAY_TOKEN_FILE) as f:
            return json.load(f)
    return {}


def _save_token(token_data: dict):
    EBAY_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(EBAY_TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)


def _is_token_expired(token_data: dict) -> bool:
    return time.time() >= token_data.get("expires_at", 0) - 60


def _refresh_access_token(token_data: dict) -> str:
    refresh_token = token_data.get("refresh_token", "")
    if not refresh_token:
        raise RuntimeError(
            "refresh_token が見つかりません。setup_ebay_oauth.py を実行してください。"
        )

    credentials = b64encode(f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}".encode()).decode()
    resp = requests.post(
        f"{EBAY_API_BASE}/identity/v1/oauth2/token",
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout=15,
    )
    if resp.status_code != 200:
        logger.error(f"eBayトークン更新失敗: {resp.status_code} {resp.text[:500]}")
        resp.raise_for_status()

    data = resp.json()
    token_data["access_token"] = data["access_token"]
    token_data["expires_at"] = time.time() + data.get("expires_in", 7200)
    _save_token(token_data)
    logger.info("eBayアクセストークンを更新しました")
    return data["access_token"]


def get_access_token() -> str:
    """有効なアクセストークンを返す（必要なら自動更新）"""
    token_data = _load_token()
    if not token_data:
        raise RuntimeError(
            "eBayトークンが見つかりません。setup_ebay_oauth.py を実行してください。"
        )
    if _is_token_expired(token_data):
        return _refresh_access_token(token_data)
    return token_data["access_token"]


def _auth_headers() -> dict:
    return {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Content-Language": "en-US",
    }


# ── Browse API 用 Client Credentials トークン ────────────

_browse_token_cache: dict = {"access_token": "", "expires_at": 0}


def _get_browse_token() -> str:
    """Browse API 用の Client Credentials トークンを取得（公開情報検索用）"""
    global _browse_token_cache
    if time.time() < _browse_token_cache.get("expires_at", 0) - 60:
        return _browse_token_cache["access_token"]

    credentials = b64encode(f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}".encode()).decode()
    resp = requests.post(
        f"{EBAY_API_BASE}/identity/v1/oauth2/token",
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        },
        timeout=15,
    )
    if resp.status_code != 200:
        logger.error(
            f"Browse API トークン取得失敗: {resp.status_code} {resp.text[:300]}"
        )
        resp.raise_for_status()

    data = resp.json()
    _browse_token_cache["access_token"] = data["access_token"]
    _browse_token_cache["expires_at"] = time.time() + data.get("expires_in", 7200)
    logger.info("Browse API トークンを取得しました")
    return data["access_token"]


def _browse_headers() -> dict:
    return {
        "Authorization": f"Bearer {_get_browse_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ── Sell Inventory API ────────────────────────────────────


def get_active_listings() -> list[EbayItem]:
    """
    アクティブ出品を全件取得。
    1) まず Sell Inventory API を試行
    2) 0件の場合は Trading API (GetMyeBaySelling) にフォールバック
    """
    items = _get_active_listings_inventory_api()
    if items:
        return items

    # Sell Inventory API で0件 → Trading API にフォールバック
    logger.info("Sell Inventory API で0件。Trading API にフォールバックします...")
    return get_active_listings_trading()


def _get_active_listings_inventory_api() -> list[EbayItem]:
    """Sell Inventory API からアクティブ出品を取得"""
    headers = _auth_headers()

    # 1) 全オファー取得 → SKU, 価格, listing_id, offer_id
    offers_by_sku: dict[str, dict] = {}
    offset = 0
    while True:
        url = f"{EBAY_API_BASE}/sell/inventory/v1/offer?limit={EBAY_PAGE_SIZE}&offset={offset}"
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"Offer API エラー: {resp.status_code} {resp.text[:200]}")
            break
        data = resp.json()
        for offer in data.get("offers", []):
            sku = offer.get("sku", "")
            status = offer.get("status", "")
            marketplace = offer.get("marketplaceId", "")
            if (
                status == "ACTIVE"
                and sku
                and (not marketplace or marketplace == "EBAY_US")
            ):
                price_val = (
                    offer.get("pricingSummary", {}).get("price", {}).get("value", "0")
                )
                offers_by_sku[sku] = {
                    "price_usd": float(price_val),
                    "listing_id": offer.get("listingId", ""),
                    "offer_id": offer.get("offerId", ""),
                    "category_id": offer.get("categoryId", ""),
                }
        total = data.get("total", 0)
        offset += EBAY_PAGE_SIZE
        if offset >= total:
            break

    if not offers_by_sku:
        logger.info("Sell Inventory API: アクティブな出品が見つかりません")
        return []

    logger.info(f"eBayアクティブ出品 (Inventory API): {len(offers_by_sku)}件")

    # 2) Inventory Item 取得 → タイトル, 在庫数, 画像, スペック
    items: list[EbayItem] = []
    offset = 0
    while True:
        url = f"{EBAY_API_BASE}/sell/inventory/v1/inventory_item?limit={EBAY_PAGE_SIZE}&offset={offset}"
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            break
        data = resp.json()
        for inv in data.get("inventoryItems", []):
            sku = inv.get("sku", "")
            if sku not in offers_by_sku:
                continue
            offer_info = offers_by_sku[sku]
            product = inv.get("product", {})
            quantity = (
                inv.get("availability", {})
                .get("shipToLocationAvailability", {})
                .get("quantity", 0)
            )
            image_urls = [
                img.get("imageUrl", "") for img in product.get("imageUrls", [])
            ]

            items.append(
                EbayItem(
                    item_id=offer_info["listing_id"],
                    sku=sku,
                    title=product.get("title", sku),
                    price_usd=offer_info["price_usd"],
                    quantity=quantity,
                    is_out_of_stock=(quantity == 0),
                    listing_id=offer_info["listing_id"],
                    category_id=offer_info.get("category_id", ""),
                    condition=inv.get("condition", ""),
                    image_urls=image_urls,
                    item_specifics=product.get("aspects", {}),
                    description=product.get("description", ""),
                    offer_id=offer_info.get("offer_id", ""),
                )
            )

        total = data.get("total", 0)
        offset += EBAY_PAGE_SIZE
        if offset >= total:
            break

    logger.info(
        f"在庫情報取得完了 (Inventory API): {len(items)}件"
        f"（うち在庫切れ {sum(1 for i in items if i.is_out_of_stock)}件）"
    )
    return items


def get_out_of_stock_items() -> list[EbayItem]:
    """在庫切れアイテムのみ返す"""
    return [item for item in get_active_listings() if item.is_out_of_stock]


# ── Trading API (フォールバック) ─────────────────────────


def get_active_listings_trading() -> list[EbayItem]:
    """Trading API (GetMyeBaySelling) でアクティブ出品を取得。eBay US のみ。"""
    token = get_access_token()
    url = "https://api.ebay.com/ws/api.dll"
    ns = "urn:ebay:apis:eBLBaseComponents"

    items: list[EbayItem] = []
    page = 1

    while True:
        xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<GetMyeBaySellingRequest xmlns="{ns}">
  <ActiveList>
    <Sort>TimeLeft</Sort>
    <Pagination>
      <EntriesPerPage>200</EntriesPerPage>
      <PageNumber>{page}</PageNumber>
    </Pagination>
  </ActiveList>
</GetMyeBaySellingRequest>"""

        resp = requests.post(
            url,
            data=xml_body.encode("utf-8"),
            headers={
                "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
                "X-EBAY-API-CALL-NAME": "GetMyeBaySelling",
                "X-EBAY-API-SITEID": "0",
                "X-EBAY-API-IAF-TOKEN": token,
                "Content-Type": "text/xml;charset=utf-8",
            },
            timeout=60,
        )
        if resp.status_code != 200:
            logger.error(f"Trading API エラー: {resp.status_code}")
            break

        root = ET.fromstring(resp.text)
        ns_map = {"e": ns}

        ack = root.findtext("e:Ack", namespaces=ns_map)
        if ack not in ("Success", "Warning"):
            errors = root.findall(".//e:ShortMessage", namespaces=ns_map)
            logger.error(
                f"Trading API: {errors[0].text if errors else 'Unknown error'}"
            )
            break

        for item in root.findall(
            ".//e:ActiveList/e:ItemArray/e:Item", namespaces=ns_map
        ):
            site = item.findtext("e:Site", "", namespaces=ns_map)
            if site and site != "US":
                continue

            item_id = item.findtext("e:ItemID", "", namespaces=ns_map)
            title = item.findtext("e:Title", "", namespaces=ns_map)

            # 価格: ConvertedCurrentPrice (USD) を優先、なければ CurrentPrice
            price_text = item.findtext(
                "e:SellingStatus/e:ConvertedCurrentPrice", "", namespaces=ns_map
            )
            if not price_text:
                price_text = item.findtext(
                    "e:SellingStatus/e:CurrentPrice", "0", namespaces=ns_map
                )
            quantity = int(item.findtext("e:QuantityAvailable", "0", namespaces=ns_map))

            # SKU: あれば使う、なければ item_id を SKU として使用
            sku = item.findtext("e:SKU", "", namespaces=ns_map) or item_id

            items.append(
                EbayItem(
                    item_id=item_id,
                    sku=sku,
                    title=title,
                    price_usd=float(price_text),
                    quantity=quantity,
                    is_out_of_stock=(quantity == 0),
                    listing_id=item_id,
                    category_name=site or "",
                )
            )

        total_pages = int(
            root.findtext(
                ".//e:ActiveList/e:PaginationResult/e:TotalNumberOfPages",
                "1",
                namespaces=ns_map,
            )
        )
        if page >= total_pages:
            break
        page += 1

    logger.info(f"Trading API 取得完了: {len(items)}件")
    return items


# ── Browse API (公開情報・競合分析) ───────────────────────


def search_ebay(query: str, limit: int = 50, category_id: str = "") -> list[dict]:
    """eBay Browse API で商品検索（公開情報・Client Credentials トークン使用）"""
    headers = _browse_headers()
    params = {"q": query, "limit": min(limit, 200)}
    if category_id:
        params["category_ids"] = category_id

    url = f"{EBAY_API_BASE}/buy/browse/v1/item_summary/search"
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    if resp.status_code != 200:
        logger.warning(f"Browse API検索エラー: {resp.status_code}")
        return []

    results = []
    for item in resp.json().get("itemSummaries", []):
        results.append(
            {
                "item_id": item.get("itemId", ""),
                "title": item.get("title", ""),
                "price": float(item.get("price", {}).get("value", 0)),
                "currency": item.get("price", {}).get("currency", "USD"),
                "condition": item.get("condition", ""),
                "image_url": item.get("image", {}).get("imageUrl", ""),
                "item_url": item.get("itemWebUrl", ""),
                "seller": item.get("seller", {}).get("username", ""),
                "seller_feedback": item.get("seller", {}).get("feedbackPercentage", ""),
                "category_id": item.get("categories", [{}])[0].get("categoryId", "")
                if item.get("categories")
                else "",
            }
        )

    return results


def get_item_details(item_id: str) -> Optional[dict]:
    """Browse API で単品の詳細情報を取得（Client Credentials トークン使用）"""
    headers = _browse_headers()
    url = f"{EBAY_API_BASE}/buy/browse/v1/item/{item_id}"
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code != 200:
        return None
    return resp.json()


# ── Browse API ディスカバリー検索 ──────────────────────────


def search_ebay_discover(
    query: str,
    limit: int = 50,
    category_id: str = "",
    price_min: float = 0,
    price_max: float = 0,
    condition_ids: str = "",
) -> dict:
    """
    Browse API で商品を検索し、需要指標（total）付きで返す。
    filter で価格帯・状態を絞り込み可能。
    """
    headers = _browse_headers()

    params = {
        "q": query,
        "limit": min(limit, 200),
        "fieldgroups": "EXTENDED",
    }
    if category_id:
        params["category_ids"] = category_id

    # フィルタ構築
    filters = []
    if price_min > 0 or price_max > 0:
        lo = f"{price_min:.0f}" if price_min > 0 else ""
        hi = f"{price_max:.0f}" if price_max > 0 else ""
        filters.append(f"price:[{lo}..{hi}],priceCurrency:USD")
    if condition_ids:
        # "1000,3000" → "{1000|3000}"
        ids = "|".join(condition_ids.split(","))
        filters.append(f"conditionIds:{{{ids}}}")
    if filters:
        params["filter"] = ",".join(filters)

    url = f"{EBAY_API_BASE}/buy/browse/v1/item_summary/search"
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    if resp.status_code != 200:
        logger.warning(
            f"Browse API discover error: {resp.status_code} {resp.text[:200]}"
        )
        return {"items": [], "total": 0}

    data = resp.json()
    total = data.get("total", 0)

    items = []
    for item in data.get("itemSummaries", []):
        # soldQuantity 取得（マルチ数量リスティング）
        qty_sold = 0
        for avail in item.get("estimatedAvailabilities") or []:
            qty_sold += avail.get("soldQuantity", 0)

        items.append(
            {
                "item_id": item.get("itemId", ""),
                "title": item.get("title", ""),
                "price": float(item.get("price", {}).get("value", 0)),
                "currency": item.get("price", {}).get("currency", "USD"),
                "condition": item.get("condition", ""),
                "condition_id": item.get("conditionId", ""),
                "image_url": item.get("image", {}).get("imageUrl", ""),
                "item_url": item.get("itemWebUrl", ""),
                "seller": item.get("seller", {}).get("username", ""),
                "seller_feedback": item.get("seller", {}).get("feedbackScore", 0),
                "sold_quantity": qty_sold,
                "buying_options": item.get("buyingOptions", []),
                "category_id": (
                    item.get("categories", [{}])[0].get("categoryId", "")
                    if item.get("categories")
                    else ""
                ),
                "item_location": item.get("itemLocation", {}).get("country", ""),
            }
        )

    return {"items": items, "total": total}


# ── Finding API (完了リスト — 売れた商品分析) ─────────────


def search_ebay_sold(query: str, limit: int = 50, category_id: str = "") -> list[dict]:
    """
    eBay Browse API で完了リスト（Sold Items）を検索。
    filter: buyingOptions={FIXED_PRICE}, conditionIds 等を活用。

    注: Browse API は「sold」フィルタ未対応のため、
    Finding API (findCompletedItems) を使う。
    """
    headers = _browse_headers()

    # Browse API には sold filter がないため、
    # アクティブ出品の「soldQuantity」フィールドで代用
    params = {
        "q": query,
        "limit": min(limit, 200),
        "fieldgroups": "EXTENDED",
    }
    if category_id:
        params["category_ids"] = category_id

    url = f"{EBAY_API_BASE}/buy/browse/v1/item_summary/search"
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    if resp.status_code != 200:
        logger.warning(f"Browse API sold search error: {resp.status_code}")
        return []

    results = []
    for item in resp.json().get("itemSummaries", []):
        sold_qty = item.get("estimatedAvailabilities", [{}])
        qty_sold = 0
        for avail in sold_qty:
            qty_sold += avail.get("soldQuantity", 0)

        results.append(
            {
                "item_id": item.get("itemId", ""),
                "title": item.get("title", ""),
                "price": float(item.get("price", {}).get("value", 0)),
                "currency": item.get("price", {}).get("currency", "USD"),
                "condition": item.get("condition", ""),
                "image_url": item.get("image", {}).get("imageUrl", ""),
                "item_url": item.get("itemWebUrl", ""),
                "seller": item.get("seller", {}).get("username", ""),
                "sold_quantity": qty_sold,
                "category_id": (
                    item.get("categories", [{}])[0].get("categoryId", "")
                    if item.get("categories")
                    else ""
                ),
            }
        )

    # 売れた数量順でソート
    results.sort(key=lambda x: x["sold_quantity"], reverse=True)
    return results


# ── 売上取得 (Trading API GetOrders) ─────────────────────


def get_recent_orders(days: int = 30) -> list[dict]:
    """Trading API (GetOrders) で最近の注文を取得する。"""
    token = get_access_token()
    from_date = (datetime.utcnow() - timedelta(days=days)).strftime(
        "%Y-%m-%dT00:00:00.000Z"
    )
    to_date = datetime.utcnow().strftime("%Y-%m-%dT23:59:59.000Z")

    xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<GetOrdersRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{token}</eBayAuthToken>
    </RequesterCredentials>
    <CreateTimeFrom>{from_date}</CreateTimeFrom>
    <CreateTimeTo>{to_date}</CreateTimeTo>
    <OrderRole>Seller</OrderRole>
    <OrderStatus>Completed</OrderStatus>
    <Pagination>
        <EntriesPerPage>100</EntriesPerPage>
        <PageNumber>1</PageNumber>
    </Pagination>
</GetOrdersRequest>"""

    headers = {
        "X-EBAY-API-SITEID": "0",
        "X-EBAY-API-COMPATIBILITY-LEVEL": "1349",
        "X-EBAY-API-CALL-NAME": "GetOrders",
        "Content-Type": "text/xml",
    }

    resp = requests.post(
        f"{EBAY_API_BASE}/ws/api.dll",
        headers=headers,
        data=xml_body.encode("utf-8"),
        timeout=60,
    )

    if resp.status_code != 200:
        logger.error(f"GetOrders failed: {resp.status_code}")
        return []

    ns_map = {"e": "urn:ebay:apis:eBLBaseComponents"}
    root = ET.fromstring(resp.text)

    ack = root.findtext("e:Ack", "", namespaces=ns_map)
    if ack not in ("Success", "Warning"):
        errors = root.findall(".//e:Errors/e:ShortMessage", namespaces=ns_map)
        error_msgs = [e.text for e in errors if e.text]
        logger.error(f"GetOrders error: {error_msgs}")
        return []

    orders = []
    for order_el in root.findall(".//e:OrderArray/e:Order", namespaces=ns_map):
        order_id = order_el.findtext("e:OrderID", "", namespaces=ns_map)
        total_str = order_el.findtext("e:Total", "0", namespaces=ns_map)
        created = order_el.findtext("e:CreatedTime", "", namespaces=ns_map)

        # 注文内のアイテム
        items = []
        for txn in order_el.findall(
            ".//e:TransactionArray/e:Transaction", namespaces=ns_map
        ):
            item_el = txn.find("e:Item", namespaces=ns_map)
            if item_el is None:
                continue
            item_id = item_el.findtext("e:ItemID", "", namespaces=ns_map)
            title = item_el.findtext("e:Title", "", namespaces=ns_map)
            sku = item_el.findtext("e:SKU", "", namespaces=ns_map) or item_id
            qty = int(txn.findtext("e:QuantityPurchased", "1", namespaces=ns_map))
            price_str = txn.findtext("e:TransactionPrice", "0", namespaces=ns_map)

            items.append(
                {
                    "item_id": item_id,
                    "sku": sku,
                    "title": title,
                    "quantity": qty,
                    "price_usd": float(price_str),
                }
            )

        # 追跡番号（ShipmentTrackingDetails から取得）
        tracking_details = order_el.findall(
            ".//e:ShippingDetails/e:ShipmentTrackingDetails", namespaces=ns_map
        )
        tracking_numbers = []
        shipping_carrier = ""
        for td in tracking_details:
            tn = td.findtext("e:ShipmentTrackingNumber", "", namespaces=ns_map)
            carrier = td.findtext("e:ShippingCarrierUsed", "", namespaces=ns_map)
            if tn:
                tracking_numbers.append(tn)
            if carrier and not shipping_carrier:
                shipping_carrier = carrier

        # バイヤー情報
        buyer_id = order_el.findtext(".//e:BuyerUserID", "", namespaces=ns_map)
        buyer_name = order_el.findtext(
            ".//e:ShippingAddress/e:Name", "", namespaces=ns_map
        )
        buyer_country = order_el.findtext(
            ".//e:ShippingAddress/e:CountryName", "", namespaces=ns_map
        )
        shipping_cost = order_el.findtext(
            ".//e:ShippingServiceSelected/e:ShippingServiceCost", "0", namespaces=ns_map
        )

        orders.append(
            {
                "order_id": order_id,
                "total_usd": float(total_str),
                "created_time": created,
                "buyer_id": buyer_id,
                "buyer_name": buyer_name,
                "buyer_country": buyer_country,
                "shipping_cost_usd": float(shipping_cost),
                "tracking_number": tracking_numbers[0] if tracking_numbers else "",
                "shipping_carrier": shipping_carrier,
                "items": items,
            }
        )

    logger.info(f"GetOrders: {len(orders)}件の注文を取得")
    return orders


def get_all_orders(from_date: str = "", to_date: str = "") -> list[dict]:
    """Fulfillment API で全注文を取得（90日制限なし、最大3年）。

    Args:
        from_date: 開始日 "YYYY-MM-DD"（空の場合は1年前）
        to_date: 終了日 "YYYY-MM-DD"（空の場合は今日）

    Returns:
        get_recent_orders と同じ形式の注文リスト
    """
    token = get_access_token()

    if not from_date:
        from_date = (datetime.utcnow() - timedelta(days=365)).strftime("%Y-%m-%d")
    if not to_date:
        to_date = datetime.utcnow().strftime("%Y-%m-%d")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    all_orders = []
    offset = 0
    limit = 50

    # from_dateをdatetimeに変換（フィルタリング用）
    from_dt = None
    if from_date:
        try:
            from_dt = datetime.strptime(from_date, "%Y-%m-%d")
        except ValueError:
            pass

    while True:
        # 日付フィルタはeBay側の時刻検証問題を回避するため使用しない
        filter_str = "orderfulfillmentstatus:{FULFILLED|IN_PROGRESS}"
        url = (
            f"{EBAY_API_BASE}/sell/fulfillment/v1/order"
            f"?filter={filter_str}"
            f"&limit={limit}&offset={offset}"
        )

        resp = requests.get(url, headers=headers, timeout=60)
        if resp.status_code != 200:
            logger.error(f"Fulfillment API error: {resp.status_code} {resp.text[:200]}")
            break

        data = resp.json()
        api_orders = data.get("orders", [])
        if not api_orders:
            break

        for o in api_orders:
            order_id = o.get("orderId", "")
            created = o.get("creationDate", "")

            # from_dateフィルタ（クライアント側）
            if from_dt and created:
                try:
                    order_dt = datetime.strptime(created[:19], "%Y-%m-%dT%H:%M:%S")
                    if order_dt < from_dt:
                        continue
                except ValueError:
                    pass

            # バイヤー情報
            buyer_info = o.get("buyer", {})
            buyer_id = buyer_info.get("username", "")
            ship_to = (
                o.get("fulfillmentStartInstructions", [{}])[0]
                .get("shippingStep", {})
                .get("shipTo", {})
            )
            buyer_name = ship_to.get("fullName", "")
            buyer_country = ship_to.get("contactAddress", {}).get("countryCode", "")

            # 追跡番号 — fulfillmentHrefs のURL末尾に含まれる
            tracking_number = ""
            shipping_carrier = ""
            for href in o.get("fulfillmentHrefs", []):
                # URL: .../shipping_fulfillment/EM1013088671094FE...
                parts = href.rstrip("/").split("/")
                if parts:
                    tn_candidate = parts[-1]
                    if len(tn_candidate) > 8:  # 追跡番号は十分長い
                        tracking_number = tn_candidate
                        break

            # shipping carrier from shippingStep
            for fh in o.get("fulfillmentStartInstructions", []):
                sc = fh.get("shippingStep", {}).get("shippingServiceCode", "")
                if sc:
                    shipping_carrier = sc
                    break

            # アイテム
            items = []
            for li in o.get("lineItems", []):
                item_id = li.get("legacyItemId", "")
                sku = li.get("sku", "") or item_id
                title = li.get("title", "")
                qty = li.get("quantity", 1)
                price_val = float(li.get("lineItemCost", {}).get("value", "0"))

                items.append(
                    {
                        "item_id": item_id,
                        "sku": sku,
                        "title": title,
                        "quantity": qty,
                        "price_usd": price_val,
                    }
                )

            total_val = float(
                o.get("pricingSummary", {}).get("total", {}).get("value", "0")
            )
            shipping_cost_val = float(
                o.get("pricingSummary", {}).get("deliveryCost", {}).get("value", "0")
            )
            # eBay手数料差引後の実受取額
            total_due_seller = float(
                o.get("paymentSummary", {}).get("totalDueSeller", {}).get("value", "0")
            )
            # eBay手数料 = 売上 - 実受取額
            ebay_fees_actual = (
                round(total_val - total_due_seller, 2) if total_due_seller else 0
            )

            all_orders.append(
                {
                    "order_id": order_id,
                    "total_usd": total_val,
                    "created_time": created,
                    "buyer_id": buyer_id,
                    "buyer_name": buyer_name,
                    "buyer_country": buyer_country,
                    "shipping_cost_usd": shipping_cost_val,
                    "tracking_number": tracking_number,
                    "shipping_carrier": shipping_carrier,
                    "ebay_fees_usd": ebay_fees_actual,
                    "items": items,
                }
            )

        total_count = data.get("total", 0)
        offset += limit
        logger.info(f"Fulfillment API: {len(all_orders)}/{total_count} 件取得済み")

        if offset >= total_count:
            break

    logger.info(f"Fulfillment API: 合計 {len(all_orders)} 件の注文を取得")
    return all_orders


# ── バイヤーメッセージ (Trading API GetMyMessages) ────────


def get_buyer_messages(days: int = 7, limit: int = 20) -> list[dict]:
    """Trading API (GetMyMessages) でバイヤーメッセージを取得する。"""
    token = get_access_token()
    from_date = (datetime.utcnow() - timedelta(days=days)).strftime(
        "%Y-%m-%dT00:00:00.000Z"
    )

    xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<GetMyMessagesRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{token}</eBayAuthToken>
    </RequesterCredentials>
    <FolderID>0</FolderID>
    <StartTime>{from_date}</StartTime>
    <Pagination>
        <EntriesPerPage>{limit}</EntriesPerPage>
        <PageNumber>1</PageNumber>
    </Pagination>
    <DetailLevel>ReturnMessages</DetailLevel>
</GetMyMessagesRequest>"""

    headers = {
        "X-EBAY-API-SITEID": "0",
        "X-EBAY-API-COMPATIBILITY-LEVEL": "1349",
        "X-EBAY-API-CALL-NAME": "GetMyMessages",
        "Content-Type": "text/xml",
    }

    resp = requests.post(
        f"{EBAY_API_BASE}/ws/api.dll",
        headers=headers,
        data=xml_body.encode("utf-8"),
        timeout=60,
    )

    if resp.status_code != 200:
        logger.error(f"GetMyMessages failed: {resp.status_code}")
        return []

    ns_map = {"e": "urn:ebay:apis:eBLBaseComponents"}
    root = ET.fromstring(resp.text)

    ack = root.findtext("e:Ack", "", namespaces=ns_map)
    if ack not in ("Success", "Warning"):
        return []

    messages = []
    for msg_el in root.findall(".//e:Messages/e:Message", namespaces=ns_map):
        msg_id = msg_el.findtext("e:MessageID", "", namespaces=ns_map)
        sender = msg_el.findtext("e:Sender", "", namespaces=ns_map)
        subject = msg_el.findtext("e:Subject", "", namespaces=ns_map)
        body = msg_el.findtext("e:Text", "", namespaces=ns_map)
        received = msg_el.findtext("e:ReceiveDate", "", namespaces=ns_map)
        is_read = msg_el.findtext("e:Read", "false", namespaces=ns_map) == "true"
        item_id = msg_el.findtext("e:ItemID", "", namespaces=ns_map)
        responded = msg_el.findtext("e:Responded", "false", namespaces=ns_map) == "true"

        messages.append(
            {
                "message_id": msg_id,
                "sender": sender,
                "subject": subject,
                "body": body,
                "received_date": received,
                "is_read": is_read,
                "item_id": item_id,
                "responded": responded,
            }
        )

    logger.info(f"GetMyMessages: {len(messages)}件のメッセージを取得")
    return messages


# ── カテゴリ Item Specifics 取得 (Taxonomy API) ──────────


def get_category_aspects(category_id: str) -> dict:
    """
    Taxonomy API でカテゴリの必須/推奨 Item Specifics を取得する。
    Returns: {"required": [...], "recommended": [...]}
    """
    headers = _auth_headers()
    # Taxonomy API — カテゴリツリー ID 0 = eBay US
    url = (
        f"{EBAY_API_BASE}/commerce/taxonomy/v1/category_tree/0"
        f"/get_item_aspects_for_category?category_id={category_id}"
    )
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code != 200:
        logger.warning(f"Taxonomy API エラー: {resp.status_code} {resp.text[:300]}")
        return {"required": [], "recommended": [], "error": f"HTTP {resp.status_code}"}

    data = resp.json()
    required = []
    recommended = []

    for aspect in data.get("aspects", []):
        name = aspect.get("localizedAspectName", "")
        constraint = aspect.get("aspectConstraint", {})
        mode = constraint.get("aspectUsage", "RECOMMENDED")
        values = [
            v.get("localizedValue", "") for v in aspect.get("aspectValues", [])[:20]
        ]
        entry = {
            "name": name,
            "values": values,
            "data_type": constraint.get("aspectDataType", "STRING"),
        }

        if mode == "REQUIRED":
            required.append(entry)
        else:
            recommended.append(entry)

    logger.info(
        f"カテゴリ {category_id} Aspects: 必須{len(required)}件, 推奨{len(recommended)}件"
    )
    return {
        "category_id": category_id,
        "required": required,
        "recommended": recommended,
    }


# ── 画像アップロード (UploadSiteHostedPictures) ───────────


def upload_picture_to_ebay(image_bytes: bytes, filename: str = "image.jpg") -> str:
    """eBay サイトホスト画像として画像をアップロードし、公開 URL を返す。

    eBay Trading API UploadSiteHostedPictures を使用。
    成功すれば 'https://i.ebayimg.com/...' 形式の URL を返す。
    失敗すれば空文字列を返す。
    """
    token = get_access_token()
    ns = "urn:ebay:apis:eBLBaseComponents"

    xml_part = f"""<?xml version="1.0" encoding="utf-8"?>
<UploadSiteHostedPicturesRequest xmlns="{ns}">
  <RequesterCredentials>
    <eBayAuthToken>{token}</eBayAuthToken>
  </RequesterCredentials>
  <PictureName>{filename}</PictureName>
  <PictureSet>Supersize</PictureSet>
</UploadSiteHostedPicturesRequest>"""

    ext = filename.rsplit(".", 1)[-1].lower()
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"

    resp = requests.post(
        "https://api.ebay.com/ws/api.dll",
        headers={
            "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
            "X-EBAY-API-CALL-NAME": "UploadSiteHostedPictures",
            "X-EBAY-API-SITEID": "0",
            "X-EBAY-API-IAFTOKEN": token,
        },
        files={
            "XML Payload": ("xml", xml_part.encode("utf-8"), "text/xml"),
            "image": (filename, image_bytes, mime),
        },
        timeout=60,
    )

    if resp.status_code != 200:
        logger.warning(
            f"UploadSiteHostedPictures HTTP {resp.status_code}: {resp.text[:200]}"
        )
        return ""

    try:
        root = ET.fromstring(resp.text)
        ack = root.findtext(f"{{{ns}}}Ack") or ""
        if ack not in ("Success", "Warning"):
            errors = root.findall(f".//{{{ns}}}Errors")
            err_msg = "; ".join(
                e.findtext(f"{{{ns}}}LongMessage")
                or e.findtext(f"{{{ns}}}ShortMessage")
                or ""
                for e in errors
            )
            logger.warning(f"UploadSiteHostedPictures failed ({ack}): {err_msg}")
            return ""
        details = root.find(f".//{{{ns}}}SiteHostedPictureDetails")
        if details is None:
            return ""
        full_url = details.findtext(f"{{{ns}}}FullURL") or ""
        logger.info(f"Picture uploaded to eBay: {full_url}")
        return full_url
    except ET.ParseError as e:
        logger.warning(f"UploadSiteHostedPictures parse error: {e}")
        return ""


# ── 既存出品の画像取得 / 画像更新 ────────────────────────


def get_item_pictures(item_id: str) -> list:
    """GetItem で既存出品の PictureURL リストを返す。失敗時は []。"""
    token = get_access_token()
    ns = "urn:ebay:apis:eBLBaseComponents"
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<GetItemRequest xmlns="{ns}">
  <RequesterCredentials><eBayAuthToken>{token}</eBayAuthToken></RequesterCredentials>
  <ItemID>{item_id}</ItemID>
  <DetailLevel>ReturnAll</DetailLevel>
  <IncludeItemSpecifics>false</IncludeItemSpecifics>
</GetItemRequest>"""
    resp = requests.post(
        "https://api.ebay.com/ws/api.dll",
        headers={
            "X-EBAY-API-SITEID": "0",
            "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
            "X-EBAY-API-CALL-NAME": "GetItem",
            "Content-Type": "text/xml",
        },
        data=xml.encode("utf-8"),
        timeout=20,
    )
    try:
        root = ET.fromstring(resp.text)
        urls = [el.text for el in root.findall(f".//{{{ns}}}PictureURL") if el.text]
        logger.info(f"GetItem pictures for {item_id}: {len(urls)} URLs")
        return urls
    except Exception as e:
        logger.warning(f"get_item_pictures error: {e}")
        return []


def revise_fixed_price_item_pictures(
    item_id: str,
    picture_urls: list,
    fulfillment_policy_id: str = "247965782010",
    payment_policy_id: str = "247965600010",
    return_policy_id: str = "247965615010",
) -> bool:
    """ReviseFixedPriceItem で既存出品の画像一覧を差し替える。

    アカウントがビジネスポリシーに opt-in 済みのため、SellerProfiles（ポリシーID）を
    必ず同梱する。欠けると eBay は legacy fields 要求とみなし
    "Seller has opted into business policies. Please use policy IDs rather than
    legacy fields" で Ack=Failure を返す（add_fixed_price_item と同じ規約）。
    """
    if not item_id or not picture_urls:
        return False
    token = get_access_token()
    ns = "urn:ebay:apis:eBLBaseComponents"
    pics_xml = "".join(f"<PictureURL>{u}</PictureURL>" for u in picture_urls)
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<ReviseFixedPriceItemRequest xmlns="{ns}">
  <RequesterCredentials><eBayAuthToken>{token}</eBayAuthToken></RequesterCredentials>
  <Item>
    <ItemID>{item_id}</ItemID>
    <SellerProfiles>
      <SellerShippingProfile><ShippingProfileID>{fulfillment_policy_id}</ShippingProfileID></SellerShippingProfile>
      <SellerPaymentProfile><PaymentProfileID>{payment_policy_id}</PaymentProfileID></SellerPaymentProfile>
      <SellerReturnProfile><ReturnProfileID>{return_policy_id}</ReturnProfileID></SellerReturnProfile>
    </SellerProfiles>
    <PictureDetails>{pics_xml}</PictureDetails>
  </Item>
</ReviseFixedPriceItemRequest>"""
    resp = requests.post(
        "https://api.ebay.com/ws/api.dll",
        headers={
            "X-EBAY-API-SITEID": "0",
            "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
            "X-EBAY-API-CALL-NAME": "ReviseFixedPriceItem",
            "Content-Type": "text/xml",
        },
        data=xml.encode("utf-8"),
        timeout=30,
    )
    success = "<Ack>Success</Ack>" in resp.text or "<Ack>Warning</Ack>" in resp.text
    if success:
        logger.info(
            f"ReviseFixedPriceItem pictures updated: item={item_id} ({len(picture_urls)} pics)"
        )
    else:
        try:
            root = ET.fromstring(resp.text)
            errs = root.findall(f".//{{{ns}}}Errors")
            msg = "; ".join(
                e.findtext(f"{{{ns}}}LongMessage")
                or e.findtext(f"{{{ns}}}ShortMessage")
                or ""
                for e in errs
            )
        except Exception:
            msg = resp.text[:200]
        logger.warning(f"ReviseFixedPriceItem failed: {msg}")
    return success


# ── 新規出品 (Trading API — eShip互換) ───────────────────


def add_fixed_price_item(
    title: str,
    description_html: str,
    category_id: str,
    price_usd: float,
    condition_id: int = 3000,
    condition_description: str = "",
    image_urls: list = None,
    item_specifics: dict = None,
    sku: str = "",
    quantity: int = 0,
    country: str = "JP",
    location: str = "Japan",
    currency: str = "USD",
    dispatch_time_max: int = 3,
    listing_duration: str = "GTC",
    fulfillment_policy_id: str = "247965782010",
    payment_policy_id: str = "247965600010",
    return_policy_id: str = "247965615010",
) -> dict:
    """Create a listing via Trading API AddFixedPriceItem.

    This is compatible with eShip (unlike Inventory API).
    Returns {'success': True, 'item_id': '...'} or {'success': False, 'error': '...'}.
    """
    token = get_access_token()
    ns = "urn:ebay:apis:eBLBaseComponents"

    # Build Item Specifics XML
    specs_xml = ""
    if item_specifics:
        specs_xml = "<ItemSpecifics>"
        for name, values in item_specifics.items():
            if isinstance(values, str):
                values = [values]
            for val in values:
                val_escaped = (
                    str(val)
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                name_escaped = (
                    str(name)
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                specs_xml += f"<NameValueList><Name>{name_escaped}</Name><Value>{val_escaped}</Value></NameValueList>"
        specs_xml += "</ItemSpecifics>"

    # Build PictureDetails XML
    pics_xml = "<PictureDetails>"
    for url in (image_urls or [])[:24]:  # eBay max 24 photos
        pics_xml += f"<PictureURL>{url}</PictureURL>"
    pics_xml += "</PictureDetails>"

    # Escape title and description
    title_escaped = (
        title[:80].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    # Description can contain HTML so we use CDATA
    cond_desc_escaped = (
        condition_description.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        if condition_description
        else ""
    )

    xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<AddFixedPriceItemRequest xmlns="{ns}">
  <Item>
    <Title>{title_escaped}</Title>
    <Description><![CDATA[{description_html.replace("]]>", "]]]]><![CDATA[>")}]]></Description>
    <PrimaryCategory><CategoryID>{category_id}</CategoryID></PrimaryCategory>
    <StartPrice currencyID="{currency}">{price_usd:.2f}</StartPrice>
    {"<ConditionID>" + str(condition_id) + "</ConditionID>" if condition_id else ""}
    {"<ConditionDescription>" + cond_desc_escaped + "</ConditionDescription>" if cond_desc_escaped else ""}
    <Country>{country}</Country>
    <Location>{location}</Location>
    <Currency>{currency}</Currency>
    <DispatchTimeMax>{dispatch_time_max}</DispatchTimeMax>
    <ListingDuration>{listing_duration}</ListingDuration>
    <ListingType>FixedPriceItem</ListingType>
    <Quantity>{quantity}</Quantity>
    {pics_xml}
    {specs_xml}
    {"<SKU>" + sku + "</SKU>" if sku else ""}
    <Site>US</Site>
    <SellerProfiles>
      <SellerShippingProfile><ShippingProfileID>{fulfillment_policy_id}</ShippingProfileID></SellerShippingProfile>
      <SellerPaymentProfile><PaymentProfileID>{payment_policy_id}</PaymentProfileID></SellerPaymentProfile>
      <SellerReturnProfile><ReturnProfileID>{return_policy_id}</ReturnProfileID></SellerReturnProfile>
    </SellerProfiles>
  </Item>
</AddFixedPriceItemRequest>"""

    resp = requests.post(
        "https://api.ebay.com/ws/api.dll",
        data=xml_body.encode("utf-8"),
        headers={
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1349",
            "X-EBAY-API-CALL-NAME": "AddFixedPriceItem",
            "X-EBAY-API-SITEID": "0",
            "X-EBAY-API-IAF-TOKEN": token,
            "Content-Type": "text/xml;charset=utf-8",
        },
        timeout=30,
    )

    root = ET.fromstring(resp.text)
    ns_map = {"e": ns}
    ack = root.findtext("e:Ack", namespaces=ns_map) or ""

    # Fallback: try without namespace (some eBay responses omit it)
    if not ack:
        ack = root.findtext("Ack") or ""

    logger.info(f"Trading API Ack={ack} for SKU={sku}")

    if ack in ("Success", "Warning"):
        item_id = (
            root.findtext("e:ItemID", namespaces=ns_map)
            or root.findtext("ItemID")
            or ""
        )
        logger.info(f"Trading API 出品成功: ItemID={item_id} SKU={sku}")
        return {"success": True, "item_id": item_id}
    else:
        errors = root.findall(".//e:Errors/e:LongMessage", namespaces=ns_map)
        if not errors:
            errors = root.findall(".//Errors/LongMessage")
        error_msg = errors[0].text if errors else resp.text[:300]
        logger.error(f"Trading API 出品失敗 (Ack={ack}): {error_msg}")
        return {"success": False, "error": error_msg}


# ── 新規出品 (Inventory API — レガシー) ──────────────────


def create_inventory_item(
    sku: str,
    product: dict,
    condition: str = "",
    condition_description: str = "",
    quantity: int = 1,
) -> dict:
    """
    Sell Inventory API で新規 Inventory Item を作成する。

    product keys:
      title, description, aspects (dict), imageUrls (list[str])
    condition: NEW, LIKE_NEW, USED_EXCELLENT, USED_VERY_GOOD, USED_GOOD, USED_ACCEPTABLE, FOR_PARTS_OR_NOT_WORKING
               Empty string = don't set (let eBay use category default)
    condition_description: Free text condition notes (shown to buyers)
    """
    headers = _auth_headers()
    url = f"{EBAY_API_BASE}/sell/inventory/v1/inventory_item/{quote(sku, safe='')}"

    body = {
        "availability": {
            "shipToLocationAvailability": {
                "quantity": quantity,
            }
        },
        "product": {
            "title": product.get("title", ""),
            "description": product.get("description", ""),
            "aspects": product.get("aspects", {}),
            "imageUrls": product.get("imageUrls", []),
        },
    }
    # Condition must be eBay enum string (not numeric ID)
    # Valid: NEW, LIKE_NEW, USED_EXCELLENT, USED_VERY_GOOD, USED_GOOD, USED_ACCEPTABLE
    if condition and condition not in ("USED",):  # "USED" alone is not valid
        body["condition"] = condition
    elif condition == "USED":
        body["condition"] = "USED_VERY_GOOD"  # Safe default
    if condition_description:
        body["conditionDescription"] = condition_description

    resp = requests.put(url, headers=headers, json=body, timeout=15)
    if resp.status_code in (200, 204):
        logger.info(f"Inventory Item 作成成功: {sku}")
        return {"success": True, "sku": sku}
    else:
        error = resp.text[:500]
        logger.error(f"Inventory Item 作成失敗: {resp.status_code} {error}")
        return {"success": False, "error": error, "status_code": resp.status_code}


def create_offer(
    sku: str,
    category_id: str,
    price_usd: float,
    condition: str = "USED_EXCELLENT",
    fulfillment_policy_id: str = "",
    payment_policy_id: str = "",
    return_policy_id: str = "",
    marketplace: str = "EBAY_US",
    listing_description: str = "",
) -> dict:
    """
    Sell Inventory API で Offer を作成する（下書き状態）。
    Offer を publish するまで eBay には公開されない。
    """
    headers = _auth_headers()
    url = f"{EBAY_API_BASE}/sell/inventory/v1/offer"

    body = {
        "sku": sku,
        "marketplaceId": marketplace,
        "format": "FIXED_PRICE",
        "categoryId": category_id,
        "merchantLocationKey": "JP_WAREHOUSE",
        "pricingSummary": {
            "price": {
                "value": str(round(price_usd, 2)),
                "currency": "USD",
            }
        },
        "listingPolicies": {
            # Default policies — M Speed Pak Expedited
            "fulfillmentPolicyId": fulfillment_policy_id or "247965782010",
            "paymentPolicyId": payment_policy_id or "247965600010",
            "returnPolicyId": return_policy_id or "247965615010",
        },
    }

    if listing_description:
        body["listingDescription"] = listing_description

    resp = requests.post(url, headers=headers, json=body, timeout=15)
    if resp.status_code in (200, 201):
        data = resp.json()
        offer_id = data.get("offerId", "")
        logger.info(f"Offer 作成成功: {sku} → Offer ID {offer_id}")
        return {"success": True, "sku": sku, "offer_id": offer_id}
    else:
        error = resp.text[:500]
        logger.error(f"Offer 作成失敗: {resp.status_code} {error}")
        return {"success": False, "error": error, "status_code": resp.status_code}


def publish_offer(offer_id: str) -> dict:
    """
    Offer を eBay に公開する。公開されるとアクティブ出品になる。
    """
    headers = _auth_headers()
    url = f"{EBAY_API_BASE}/sell/inventory/v1/offer/{offer_id}/publish"

    resp = requests.post(url, headers=headers, timeout=15)
    if resp.status_code in (200, 201):
        data = resp.json()
        listing_id = data.get("listingId", "")
        logger.info(f"Offer 公開成功: {offer_id} → Listing ID {listing_id}")
        return {"success": True, "offer_id": offer_id, "listing_id": listing_id}
    else:
        error = resp.text[:2000]
        logger.error(f"Offer 公開失敗: {resp.status_code} {error[:500]}")
        return {"success": False, "error": error, "status_code": resp.status_code}


# Store category keyword → Store Category ID mapping
_STORE_CATEGORY_ID_MAP = {
    # Audio Equipment
    "amplifier": "44508405016",
    "amp ": "44508405016",
    "receiver": "44508405016",
    "turntable": "44508406016",
    "record player": "44508406016",
    "speaker": "44508408016",
    "subwoofer": "44508408016",
    "cassette": "44675522016",
    "tape deck": "44675522016",
    "reel to reel": "44675522016",
    "cd player": "44508407016",
    "minidisc": "44508407016",
    "md player": "44508407016",
    "dat": "44508407016",
    "tuner": "44608634016",
    "walkman": "44848028016",
    "cartridge": "44509764016",
    "stylus": "44509764016",
    "dj controller": "44670713016",
    "dj mixer": "44670713016",
    "cdj": "44670713016",
    # Musical Instruments
    "guitar": "44578237016",
    "bass guitar": "44578237016",
    "synthesizer": "44509641016",
    "keyboard": "44509641016",
    "drum machine": "44509641016",
    "sampler": "44509641016",
    "effects pedal": "44509642016",
    "multi-effects": "44509642016",
    "pedal": "44509642016",
    "flute": "44870858016",
    "piccolo": "44870858016",
    "clarinet": "44870858016",
    "saxophone": "44870858016",
    "oboe": "44870858016",
    "trumpet": "44862570016",
    "trombone": "44862570016",
    "shamisen": "44509640016",
    "koto": "44509640016",
    "shakuhachi": "44509640016",
    # Cameras
    "camera": "44508417016",
    "slr": "44508417016",
    "lens": "44508420016",
    "nikkor": "44508420016",
    "medium format": "44508418016",
    "mamiya": "44508418016",
    "binocular": "44509827016",
    # Other
    "watch": "44508414016",
    "g-shock": "44508414016",
    "seiko": "44508414016",
    "fountain pen": "44508415016",
    "pen ": "44508415016",
    "samurai": "44508401016",
    "armor": "44508401016",
    "tsuba": "44508403016",
    "sword": "44508403016",
    "netsuke": "44508404016",
    "inro": "44508404016",
    "figure": "44508410016",
    "anime": "44508410016",
    "vinyl record": "44509780016",
    "lure": "44509769016",
    "fishing": "44509768016",
}


def _guess_store_category_id(title: str, description: str = "") -> str:
    """Guess store category ID from title/description keywords."""
    text = (title + " " + description).lower()
    for keyword, cat_id in _STORE_CATEGORY_ID_MAP.items():
        if keyword in text:
            return cat_id
    return ""


def set_store_category(item_id: str, store_category_id: str) -> bool:
    """Set store category on a published listing via Trading API ReviseItem."""
    if not store_category_id or not item_id:
        return False
    token = get_access_token()
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<ReviseItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">'
        "<RequesterCredentials><eBayAuthToken>"
        + token
        + "</eBayAuthToken></RequesterCredentials>"
        "<Item><ItemID>" + str(item_id) + "</ItemID>"
        "<Storefront><StoreCategoryID>"
        + str(store_category_id)
        + "</StoreCategoryID></Storefront>"
        "</Item></ReviseItemRequest>"
    )
    resp = requests.post(
        "https://api.ebay.com/ws/api.dll",
        headers={
            "X-EBAY-API-SITEID": "0",
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1349",
            "X-EBAY-API-CALL-NAME": "ReviseItem",
            "Content-Type": "text/xml",
        },
        data=xml.encode("utf-8"),
        timeout=15,
    )
    success = "<Ack>Success</Ack>" in resp.text or "<Ack>Warning</Ack>" in resp.text
    if success:
        logger.info(f"Store category set: item={item_id} cat={store_category_id}")
    else:
        logger.warning(f"Store category failed: {resp.text[:200]}")
    return success


def add_to_promoted_listing(listing_id: str, bid_percentage: float = 2.0) -> bool:
    """Add a listing to the General Promoted Listings campaign (EBAY_US, 2% fixed)."""
    campaign_id = "97284846016"  # EBAY_US General campaign
    headers = _auth_headers()
    url = f"https://api.ebay.com/sell/marketing/v1/ad_campaign/{campaign_id}/bulk_create_ads_by_listing_id"

    resp = requests.post(
        url,
        headers=headers,
        json={
            "requests": [
                {
                    "listingId": str(listing_id),
                    "bidPercentage": str(bid_percentage),
                }
            ]
        },
        timeout=15,
    )
    if resp.status_code in (200, 201):
        logger.info(f"Promoted listing added: {listing_id} at {bid_percentage}%")
        return True
    else:
        logger.warning(f"Promoted listing failed: {resp.status_code} {resp.text[:200]}")
        return False


def suggest_category(query: str) -> str:
    """Get eBay category ID suggestion for a product query using Taxonomy API.

    Builds a better search query by extracting brand + model + product type.
    Filters out clearly wrong categories (e.g., books/media for electronics).
    """
    # Categories that are obviously wrong for equipment/electronics
    # These categories require item specifics like Author, Publication Name, etc.
    _BLOCKED_CATEGORY_IDS = {
        "267",  # Books & Magazines
        "261186",  # Books
        "280",  # Magazines
        "29223",  # Textbooks
        "171228",  # Audiobooks
        "11104",  # Sheet Music
        "617",  # Records (Vinyl)
        "176984",  # Music CDs
        "176983",  # Music Cassettes
        "80131",  # Movie DVDs & Blu-ray
        "11232",  # VHS
        "2536",  # Toys & Games (too generic)
    }
    _BLOCKED_CATEGORY_NAMES_PARTIAL = [
        "book",
        "magazine",
        "publication",
        "textbook",
        "comic",
        "novel",
        "manga",
        "dvd",
        "blu-ray",
        "vhs",
    ]

    try:
        headers = _browse_headers()
        # Get category tree ID for US
        resp = requests.get(
            "https://api.ebay.com/commerce/taxonomy/v1/get_default_category_tree_id",
            headers=headers,
            params={"marketplace_id": "EBAY_US"},
            timeout=10,
        )
        if resp.status_code != 200:
            return ""
        tree_id = resp.json().get("categoryTreeId", "0")

        # Get suggestions
        resp2 = requests.get(
            f"https://api.ebay.com/commerce/taxonomy/v1/category_tree/{tree_id}/get_category_suggestions",
            headers=headers,
            params={"q": query},
            timeout=10,
        )
        if resp2.status_code == 200:
            suggestions = resp2.json().get("categorySuggestions", [])
            for suggestion in suggestions:
                cat_id = suggestion.get("category", {}).get("categoryId", "")
                cat_name = suggestion.get("category", {}).get("categoryName", "")
                cat_ancestors = suggestion.get("categoryTreeNodeAncestors", [])

                # Check if category is in blocklist by ID
                if cat_id in _BLOCKED_CATEGORY_IDS:
                    logger.info(
                        f"Skipping blocked category {cat_id} ({cat_name}) for '{query}'"
                    )
                    continue

                # Check if any ancestor is in blocklist
                ancestor_blocked = False
                for ancestor in cat_ancestors:
                    anc_id = ancestor.get("categoryId", "")
                    anc_name = ancestor.get("categoryName", "").lower()
                    if anc_id in _BLOCKED_CATEGORY_IDS:
                        ancestor_blocked = True
                        break
                    if any(
                        blocked in anc_name
                        for blocked in _BLOCKED_CATEGORY_NAMES_PARTIAL
                    ):
                        ancestor_blocked = True
                        break
                if ancestor_blocked:
                    logger.info(
                        f"Skipping category {cat_id} ({cat_name}) — ancestor in blocklist for '{query}'"
                    )
                    continue

                # Check category name itself
                if any(
                    blocked in cat_name.lower()
                    for blocked in _BLOCKED_CATEGORY_NAMES_PARTIAL
                ):
                    logger.info(
                        f"Skipping category {cat_id} ({cat_name}) — name matches blocklist for '{query}'"
                    )
                    continue

                logger.info(f"Category suggestion: {cat_id} ({cat_name}) for '{query}'")
                return cat_id

            # If all suggestions were blocked, log warning
            if suggestions:
                logger.warning(
                    f"All {len(suggestions)} category suggestions blocked for '{query}'"
                )
    except Exception as e:
        logger.debug(f"Category suggestion failed: {e}")
    return ""


def get_fulfillment_policies() -> list[dict]:
    """Account API でフルフィルメントポリシー一覧を取得"""
    headers = _auth_headers()
    url = f"{EBAY_API_BASE}/sell/account/v1/fulfillment_policy?marketplace_id=EBAY_US"
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code != 200:
        return []
    return [
        {"id": p.get("fulfillmentPolicyId", ""), "name": p.get("name", "")}
        for p in resp.json().get("fulfillmentPolicies", [])
    ]


def get_return_policies() -> list[dict]:
    """Account API でリターンポリシー一覧を取得"""
    headers = _auth_headers()
    url = f"{EBAY_API_BASE}/sell/account/v1/return_policy?marketplace_id=EBAY_US"
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code != 200:
        return []
    return [
        {"id": p.get("returnPolicyId", ""), "name": p.get("name", "")}
        for p in resp.json().get("returnPolicies", [])
    ]


def get_payment_policies() -> list[dict]:
    """Account API でペイメントポリシー一覧を取得"""
    headers = _auth_headers()
    url = f"{EBAY_API_BASE}/sell/account/v1/payment_policy?marketplace_id=EBAY_US"
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code != 200:
        return []
    return [
        {"id": p.get("paymentPolicyId", ""), "name": p.get("name", "")}
        for p in resp.json().get("paymentPolicies", [])
    ]


# ── 出品更新 ──────────────────────────────────────────────


def update_listing(sku: str, updates: dict) -> dict:
    """
    Sell Inventory API で出品情報を更新する。
    updates に含まれるフィールドのみ更新。

    updates keys: title, description, price_usd, quantity, aspects
    """
    headers = _auth_headers()
    result = {"success": False, "changes": []}

    # 1) 現在の inventory item を取得
    url = f"{EBAY_API_BASE}/sell/inventory/v1/inventory_item/{quote(sku, safe='')}"
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code != 200:
        result["error"] = f"SKU {sku} が見つかりません"
        return result

    inv_data = resp.json()

    # 2) 更新フィールドを適用
    if "title" in updates:
        inv_data.setdefault("product", {})["title"] = updates["title"]
        result["changes"].append(f"title -> {updates['title']}")

    if "description" in updates:
        inv_data.setdefault("product", {})["description"] = updates["description"]
        result["changes"].append("description updated")

    if "aspects" in updates:
        inv_data.setdefault("product", {})["aspects"] = updates["aspects"]
        result["changes"].append("aspects updated")

    if "quantity" in updates:
        inv_data.setdefault("availability", {}).setdefault(
            "shipToLocationAvailability", {}
        )["quantity"] = updates["quantity"]
        result["changes"].append(f"quantity -> {updates['quantity']}")

    # 3) PUT で更新
    resp = requests.put(url, headers=headers, json=inv_data, timeout=15)
    if resp.status_code not in (200, 204):
        result["error"] = f"更新失敗: {resp.status_code} {resp.text[:300]}"
        return result

    # 4) 価格変更は Offer API
    if "price_usd" in updates:
        price_result = _update_offer_price(sku, updates["price_usd"], headers)
        if price_result:
            result["changes"].append(f"price -> ${updates['price_usd']:.2f}")
        else:
            result["error"] = "価格更新失敗"
            return result

    result["success"] = True
    logger.info(f"出品更新完了: {sku} ({', '.join(result['changes'])})")
    return result


def _update_offer_price(sku: str, new_price: float, headers: dict) -> bool:
    """Offer API で価格を更新"""
    url = f"{EBAY_API_BASE}/sell/inventory/v1/offer"
    resp = requests.get(url, headers=headers, params={"sku": sku}, timeout=15)
    if resp.status_code != 200:
        return False
    offers = resp.json().get("offers", [])
    if not offers:
        return False

    offer = offers[0]
    offer_id = offer.get("offerId", "")
    offer["pricingSummary"]["price"]["value"] = str(new_price)

    resp = requests.put(
        f"{EBAY_API_BASE}/sell/inventory/v1/offer/{offer_id}",
        headers=headers,
        json=offer,
        timeout=15,
    )
    return resp.status_code in (200, 204)
