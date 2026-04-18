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
        raise RuntimeError("refresh_token が見つかりません。setup_ebay_oauth.py を実行してください。")

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
        raise RuntimeError("eBayトークンが見つかりません。setup_ebay_oauth.py を実行してください。")
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
        logger.error(f"Browse API トークン取得失敗: {resp.status_code} {resp.text[:300]}")
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
            if status == "ACTIVE" and sku and (not marketplace or marketplace == "EBAY_US"):
                price_val = offer.get("pricingSummary", {}).get("price", {}).get("value", "0")
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
            quantity = inv.get("availability", {}).get("shipToLocationAvailability", {}).get("quantity", 0)
            image_urls = [img.get("imageUrl", "") for img in product.get("imageUrls", [])]

            items.append(EbayItem(
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
            ))

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
            logger.error(f"Trading API: {errors[0].text if errors else 'Unknown error'}")
            break

        for item in root.findall(".//e:ActiveList/e:ItemArray/e:Item", namespaces=ns_map):
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

            items.append(EbayItem(
                item_id=item_id,
                sku=sku,
                title=title,
                price_usd=float(price_text),
                quantity=quantity,
                is_out_of_stock=(quantity == 0),
                listing_id=item_id,
                category_name=site or "",
            ))

        total_pages = int(
            root.findtext(".//e:ActiveList/e:PaginationResult/e:TotalNumberOfPages", "1", namespaces=ns_map)
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
        results.append({
            "item_id": item.get("itemId", ""),
            "title": item.get("title", ""),
            "price": float(item.get("price", {}).get("value", 0)),
            "currency": item.get("price", {}).get("currency", "USD"),
            "condition": item.get("condition", ""),
            "image_url": item.get("image", {}).get("imageUrl", ""),
            "item_url": item.get("itemWebUrl", ""),
            "seller": item.get("seller", {}).get("username", ""),
            "seller_feedback": item.get("seller", {}).get("feedbackPercentage", ""),
            "category_id": item.get("categories", [{}])[0].get("categoryId", "") if item.get("categories") else "",
        })

    return results


def get_item_details(item_id: str) -> Optional[dict]:
    """Browse API で単品の詳細情報を取得（Client Credentials トークン使用）"""
    headers = _browse_headers()
    # Browse APIはv1|{item_id}|0の形式が必要
    if not item_id.startswith("v1|"):
        item_id = f"v1|{item_id}|0"
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
        logger.warning(f"Browse API discover error: {resp.status_code} {resp.text[:200]}")
        return {"items": [], "total": 0}

    data = resp.json()
    total = data.get("total", 0)

    items = []
    for item in data.get("itemSummaries", []):
        # soldQuantity 取得（マルチ数量リスティング）
        qty_sold = 0
        for avail in (item.get("estimatedAvailabilities") or []):
            qty_sold += avail.get("soldQuantity", 0)

        items.append({
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
                if item.get("categories") else ""
            ),
            "item_location": item.get("itemLocation", {}).get("country", ""),
        })

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

        results.append({
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
                if item.get("categories") else ""
            ),
        })

    # 売れた数量順でソート
    results.sort(key=lambda x: x["sold_quantity"], reverse=True)
    return results


# ── 売上取得 (Trading API GetOrders) ─────────────────────

def get_recent_orders(days: int = 30) -> list[dict]:
    """Trading API (GetOrders) で最近の注文を取得する。"""
    token = get_access_token()
    from_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00.000Z")
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
        for txn in order_el.findall(".//e:TransactionArray/e:Transaction", namespaces=ns_map):
            item_el = txn.find("e:Item", namespaces=ns_map)
            if item_el is None:
                continue
            item_id = item_el.findtext("e:ItemID", "", namespaces=ns_map)
            title = item_el.findtext("e:Title", "", namespaces=ns_map)
            sku = item_el.findtext("e:SKU", "", namespaces=ns_map) or item_id
            qty = int(txn.findtext("e:QuantityPurchased", "1", namespaces=ns_map))
            price_str = txn.findtext("e:TransactionPrice", "0", namespaces=ns_map)

            items.append({
                "item_id": item_id,
                "sku": sku,
                "title": title,
                "quantity": qty,
                "price_usd": float(price_str),
            })

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

        orders.append({
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
        })

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
            ship_to = o.get("fulfillmentStartInstructions", [{}])[0].get("shippingStep", {}).get("shipTo", {})
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

                items.append({
                    "item_id": item_id,
                    "sku": sku,
                    "title": title,
                    "quantity": qty,
                    "price_usd": price_val,
                })

            total_val = float(o.get("pricingSummary", {}).get("total", {}).get("value", "0"))
            shipping_cost_val = float(
                o.get("pricingSummary", {}).get("deliveryCost", {}).get("value", "0")
            )
            # eBay手数料差引後の実受取額
            total_due_seller = float(
                o.get("paymentSummary", {}).get("totalDueSeller", {}).get("value", "0")
            )
            # eBay手数料 = 売上 - 実受取額
            ebay_fees_actual = round(total_val - total_due_seller, 2) if total_due_seller else 0

            all_orders.append({
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
            })

        total_count = data.get("total", 0)
        offset += limit
        logger.info(f"Fulfillment API: {len(all_orders)}/{total_count} 件取得済み")

        if offset >= total_count:
            break

    logger.info(f"Fulfillment API: 合計 {len(all_orders)} 件の注文を取得")
    return all_orders


# ── バイヤーメッセージ (Trading API GetMyMessages) ────────

def get_buyer_messages(days: int = 30, limit: int = 200) -> list[dict]:
    """Trading API (GetMyMessages) でバイヤーメッセージを全件取得する。

    2段階API呼び出し（ページネーション対応）:
    1. ReturnHeaders でメッセージID一覧を取得（全ページ）
    2. ReturnMessages + MessageIDs でメッセージ本文を取得
    """
    token = get_access_token()
    from_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00.000Z")

    headers = {
        "X-EBAY-API-SITEID": "0",
        "X-EBAY-API-COMPATIBILITY-LEVEL": "1349",
        "X-EBAY-API-CALL-NAME": "GetMyMessages",
        "Content-Type": "text/xml",
    }
    ns_map = {"e": "urn:ebay:apis:eBLBaseComponents"}

    def _fetch_headers(folder_id: int, is_sent: bool = False) -> dict:
        """指定フォルダからメッセージヘッダーを全ページ取得する。"""
        all_headers = {}
        page = 1
        per_page = min(limit, 200)  # eBay APIの最大は200件/ページ

        while True:
            xml_req = f"""<?xml version="1.0" encoding="utf-8"?>
<GetMyMessagesRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{token}</eBayAuthToken>
    </RequesterCredentials>
    <FolderID>{folder_id}</FolderID>
    <StartTime>{from_date}</StartTime>
    <Pagination>
        <EntriesPerPage>{per_page}</EntriesPerPage>
        <PageNumber>{page}</PageNumber>
    </Pagination>
    <DetailLevel>ReturnHeaders</DetailLevel>
</GetMyMessagesRequest>"""

            resp = requests.post(
                f"{EBAY_API_BASE}/ws/api.dll",
                headers=headers,
                data=xml_req.encode("utf-8"),
                timeout=60,
            )

            if resp.status_code != 200:
                logger.error(f"GetMyMessages folder={folder_id} page={page} failed: {resp.status_code}")
                break

            root = ET.fromstring(resp.text)
            ack = root.findtext("e:Ack", "", namespaces=ns_map)
            if ack not in ("Success", "Warning"):
                break

            page_msgs = root.findall(".//e:Messages/e:Message", namespaces=ns_map)
            if not page_msgs:
                break

            for msg_el in page_msgs:
                msg_id = msg_el.findtext("e:MessageID", "", namespaces=ns_map)
                if not msg_id or msg_id in all_headers:
                    continue
                subject_raw = msg_el.findtext("e:Subject", "", namespaces=ns_map)
                try:
                    subject_raw = subject_raw.encode("latin-1").decode("utf-8")
                except (UnicodeDecodeError, UnicodeEncodeError):
                    pass

                if is_sent:
                    recipient = msg_el.findtext("e:SendToName", "", namespaces=ns_map) or msg_el.findtext("e:RecipientUserID", "", namespaces=ns_map) or ""
                    all_headers[msg_id] = {
                        "message_id": msg_id,
                        "sender": "me",
                        "recipient": recipient,
                        "subject": subject_raw,
                        "body": "",
                        "received_date": msg_el.findtext("e:ReceiveDate", "", namespaces=ns_map),
                        "is_read": True,
                        "item_id": msg_el.findtext("e:ItemID", "", namespaces=ns_map),
                        "responded": True,
                        "direction": "outbound",
                    }
                else:
                    all_headers[msg_id] = {
                        "message_id": msg_id,
                        "sender": msg_el.findtext("e:Sender", "", namespaces=ns_map),
                        "subject": subject_raw,
                        "body": "",
                        "received_date": msg_el.findtext("e:ReceiveDate", "", namespaces=ns_map),
                        "is_read": msg_el.findtext("e:Read", "false", namespaces=ns_map) == "true",
                        "item_id": msg_el.findtext("e:ItemID", "", namespaces=ns_map),
                        "responded": msg_el.findtext("e:Replied", "false", namespaces=ns_map) == "true",
                    }

            # 次ページがあるか確認
            total_pages = int(root.findtext(".//e:PaginationResult/e:TotalNumberOfPages", "1", namespaces=ns_map))
            logger.info(f"GetMyMessages folder={folder_id} page={page}/{total_pages}: {len(page_msgs)} msgs")
            if page >= total_pages:
                break
            page += 1

        return all_headers

    # Step 1: 受信メッセージヘッダー（全ページ）
    msg_headers = _fetch_headers(0, is_sent=False)
    logger.info(f"GetMyMessages 受信: {len(msg_headers)} 件")

    if not msg_headers:
        logger.info("GetMyMessages: 受信0件")

    # Step 2: メッセージ本文を取得（10件ずつバッチ）
    all_ids = list(msg_headers.keys())
    for i in range(0, len(all_ids), 10):
        batch_ids = all_ids[i:i + 10]
        ids_xml = "\n".join(f"    <MessageID>{mid}</MessageID>" for mid in batch_ids)

        xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<GetMyMessagesRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{token}</eBayAuthToken>
    </RequesterCredentials>
    <MessageIDs>
{ids_xml}
    </MessageIDs>
    <DetailLevel>ReturnMessages</DetailLevel>
</GetMyMessagesRequest>"""

        resp2 = requests.post(
            f"{EBAY_API_BASE}/ws/api.dll",
            headers=headers,
            data=xml_body.encode("utf-8"),
            timeout=60,
        )

        if resp2.status_code == 200:
            root2 = ET.fromstring(resp2.text)
            ack2 = root2.findtext("e:Ack", "", namespaces=ns_map)
            if ack2 in ("Success", "Warning"):
                for msg_el in root2.findall(".//e:Messages/e:Message", namespaces=ns_map):
                    mid = msg_el.findtext("e:MessageID", "", namespaces=ns_map)
                    body_text = msg_el.findtext("e:Text", "", namespaces=ns_map)
                    if mid in msg_headers and body_text:
                        msg_headers[mid]["body"] = body_text
                    # 添付画像（MessageMedia）を抽出
                    if mid in msg_headers:
                        media_urls = []
                        for media in msg_el.findall(".//e:MessageMedia", namespaces=ns_map):
                            url = media.findtext("e:MediaURL", "", namespaces=ns_map)
                            if url:
                                media_urls.append(url)
                        if media_urls:
                            msg_headers[mid]["attachment_urls"] = media_urls

    # Step 3: 送信済みフォルダ(FolderID=1)からも全ページ取得
    sent_headers = _fetch_headers(1, is_sent=True)
    # 受信と重複するIDを除外
    sent_headers = {k: v for k, v in sent_headers.items() if k not in msg_headers}
    logger.info(f"GetMyMessages 送信: {len(sent_headers)} 件")

    # 送信メッセージの本文取得
    if sent_headers:
        sent_ids = list(sent_headers.keys())
        for i in range(0, len(sent_ids), 10):
            batch_ids = sent_ids[i:i + 10]
            ids_xml = "\n".join(f"    <MessageID>{mid}</MessageID>" for mid in batch_ids)
            xml_body_sent = f"""<?xml version="1.0" encoding="utf-8"?>
<GetMyMessagesRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{token}</eBayAuthToken>
    </RequesterCredentials>
    <MessageIDs>
{ids_xml}
    </MessageIDs>
    <DetailLevel>ReturnMessages</DetailLevel>
</GetMyMessagesRequest>"""
            resp3 = requests.post(
                f"{EBAY_API_BASE}/ws/api.dll",
                headers=headers,
                data=xml_body_sent.encode("utf-8"),
                timeout=60,
            )
            if resp3.status_code == 200:
                root3 = ET.fromstring(resp3.text)
                if root3.findtext("e:Ack", "", namespaces=ns_map) in ("Success", "Warning"):
                    for msg_el in root3.findall(".//e:Messages/e:Message", namespaces=ns_map):
                        mid = msg_el.findtext("e:MessageID", "", namespaces=ns_map)
                        body_text = msg_el.findtext("e:Text", "", namespaces=ns_map)
                        if mid in sent_headers and body_text:
                            sent_headers[mid]["body"] = body_text

    # 全メッセージを結合
    all_messages = list(msg_headers.values()) + list(sent_headers.values())

    # HTMLメッセージからテキスト抽出
    for msg in all_messages:
        if msg["body"] and msg["body"].strip().startswith("<"):
            msg["body"] = _html_to_text(msg["body"])

    logger.info(f"GetMyMessages: 受信{len(msg_headers)}件 + 送信{len(sent_headers)}件 = {len(all_messages)}件")
    return all_messages


def _html_to_text(html: str) -> str:
    """HTMLメッセージからバイヤーの本文のみを抽出する。"""
    import re
    from html.parser import HTMLParser

    class _Extractor(HTMLParser):
        """HTML→テキスト変換。<p>→段落区切り(\n\n), <br>→改行(\n)を保持。"""
        def __init__(self):
            super().__init__()
            self.parts: list[str] = []
            self.skip = False
        def handle_starttag(self, tag, attrs):
            if tag in ("style", "head", "script"):
                self.skip = True
            if tag == "br":
                self.parts.append("\n")
            if tag in ("p", "div", "tr"):
                if self.parts and self.parts[-1] != "\n":
                    self.parts.append("\n")
        def handle_endtag(self, tag):
            if tag in ("style", "head", "script"):
                self.skip = False
            if tag == "p":
                self.parts.append("\n")
        def handle_data(self, data):
            if not self.skip:
                self.parts.append(data)

    def _parse(fragment: str) -> str:
        ext = _Extractor()
        ext.feed(fragment)
        text = "".join(ext.parts).strip()
        return re.sub(r"\n{3,}", "\n\n", text)

    # UserInputtedText → ユーザーの実メッセージのみ抽出
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        user_text_div = soup.find(id="UserInputtedText")
        if user_text_div:
            text = _parse(str(user_text_div))
            # mojibake修正
            try:
                text = text.encode("latin-1").decode("utf-8")
            except (UnicodeDecodeError, UnicodeEncodeError):
                pass
            if text:
                return text

        # UserInputtedText がない場合はフォールバック
        for tag in soup(["script", "style", "head"]):
            tag.decompose()
        text = _parse(str(soup))
    except Exception:
        text = _parse(html)

    lines = text.split("\n")

    # "New message to/from:" の次の行以降が実際の本文
    # 要約行（最初の1行）は "New message to:" の前にある
    start_idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^New message( to| from)?:", stripped, re.IGNORECASE):
            start_idx = i + 1  # "New message to:" の次から開始
            break

    # 要約行をスキップして実本文から開始
    if start_idx > 0:
        lines = lines[start_idx:]

    # eBayテンプレートのノイズを除去
    clean_lines = []
    skip_patterns = [
        r"^New message:$",
        r"^New message from:$",
        r"^New message to:$",
        r"^Dear .+,$",
        r"^Herr .+$",  # ドイツ語敬称
        r"^Frau .+$",
        r"^Reply$",
        r"^Reply with offer$",
        r"^Make an offer$",
        r"^Report message$",
        r"^\(\d+\s*\)$",  # (763) フィードバックスコア
        r"^\d+$",  # 数字のみの行
        r"^- \w+$",  # - username
        r"^Item ID:",
        r"^Quantity remaining:",
        r"^End date:",
        r"^View (this item|your listing|item)$",
        r"^Respond to ",
        r"^This message was sent",
        r"^Learn more about",
        r"^Get to know",
        r"^©\s*\d{4}",
        r"^eBay International",
        r"^Your previous message",
        r"^Sent from my ",
        r"^View listing$",
        r"^Marketplace messages",
        r"^Message from eBay",
        r"^Thank you for (shopping|buying|purchasing)",
        r"^Protect your account",
        r"^Tips for buyers",
        r"^Report this message",
        r"^All rights reserved",
        r"^Item #\d+",
        r"^\*This message",
        r"^Attachment\(s\)",
        r"^eBay sent this",
        r"^If you have any questions",
        r"^Download the eBay app",
        r"^This email was sent",
        r"^Privacy|^Terms|^About eBay",
        r"^Was this message helpful",
        r"^Shop for deals",
        r"^\xa0+$",  # non-breaking space行
        r"^͏",  # invisible Unicode
    ]
    seen_content = set()
    stop_at_patterns = [
        r"^Your previous message",
        r"^Sent from my ",
        r"^Original message",
        r"^On \d{1,2}/\d{1,2}/\d{2,4}",
        r"^---+$",
        r"^Previous message",
        r"^Vorherige Nachricht",  # ドイツ語
        r"^Message précédent",  # フランス語
    ]
    content_started = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            # 段落区切り（空行）を保持
            if content_started and clean_lines and clean_lines[-1] != "":
                clean_lines.append("")
            continue
        # ストップパターン: これ以降は引用なので打ち切り
        if any(re.match(p, stripped, re.IGNORECASE) for p in stop_at_patterns):
            break
        # 引用の開始を検知（"New message to/from:" が出たら打ち切り — 既に本文開始済みの場合）
        if re.match(r"^New message (to|from):", stripped, re.IGNORECASE):
            if content_started:
                break  # 引用開始
            continue  # まだスキップフェーズ
        # パターンスキップ
        if any(re.match(p, stripped, re.IGNORECASE) for p in skip_patterns):
            continue
        # ユーザー名行（送信者名だけの行）スキップ
        if re.match(r"^[a-z0-9_.-]+$", stripped) and len(stripped) < 30:
            continue
        # フィードバックスコア括弧 (763)
        if re.match(r"^\(\d+$", stripped) or re.match(r"^\)$", stripped):
            continue
        # 重複除去
        if stripped in seen_content:
            continue
        seen_content.add(stripped)
        clean_lines.append(stripped)
        content_started = True

    result = "\n".join(clean_lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    # UTF-8 mojibake修正（Latin-1→UTF-8）
    try:
        result = result.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    return result.strip()


# ── メッセージ送信 (Trading API — 自動判定) ──

def _is_transaction_partner(item_id: str, recipient_id: str) -> bool:
    """バイヤーがその商品の取引パートナー（購入者）かどうか判定する。

    SalesRecord + Fulfillment APIで確認。購入済み→True、問い合わせのみ→False。
    """
    try:
        from database.models import get_db, SalesRecord
        db = get_db()
        # item_id経由でSalesRecordを検索
        sale = db.query(SalesRecord).filter(
            SalesRecord.item_id == item_id,
            SalesRecord.buyer_name == recipient_id,
        ).first()
        db.close()
        if sale:
            return True
        # buyer_nameが実名の場合もあるので、item_idだけでも確認
        db = get_db()
        sale_by_item = db.query(SalesRecord).filter(
            SalesRecord.item_id == item_id,
        ).first()
        db.close()
        return sale_by_item is not None
    except Exception as e:
        logger.warning(f"取引パートナー判定エラー: {e}")
        return False


def send_buyer_message(
    item_id: str,
    recipient_id: str,
    body: str,
    subject: str = "",
    image_urls: list[str] | None = None,
    parent_message_id: str = "",
) -> dict:
    """Trading API でバイヤーにメッセージを送信する。

    自動判定:
    - 購入済みバイヤー → AddMemberMessageAAQToPartner
    - 問い合わせのみ → AddMemberMessageRTQ (Response To Question)

    Args:
        item_id: eBay Item ID
        recipient_id: バイヤーのユーザーID
        body: メッセージ本文
        subject: 件名（空の場合はRe:で自動生成）
        image_urls: EPS画像URLリスト
        parent_message_id: 返信先の元メッセージID（RTQ用）

    Returns:
        {"success": bool, "error": str | None}
    """
    token = get_access_token()
    is_partner = _is_transaction_partner(item_id, recipient_id)

    # 画像添付XML生成
    media_xml = ""
    if image_urls:
        for i, url in enumerate(image_urls):
            media_xml += f"""
        <MessageMedia>
            <MediaName>image_{i + 1}</MediaName>
            <MediaURL>{url}</MediaURL>
        </MessageMedia>"""

    subject_xml = f"<Subject>{_xml_escape(subject)}</Subject>" if subject else ""

    if is_partner:
        # 購入済みバイヤー → AAQToPartner
        api_call = "AddMemberMessageAAQToPartner"
        xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<AddMemberMessageAAQToPartnerRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{token}</eBayAuthToken>
    </RequesterCredentials>
    <ItemID>{item_id}</ItemID>
    <MemberMessage>
        {subject_xml}
        <Body>{_xml_escape(body)}</Body>
        <RecipientID>{_xml_escape(recipient_id)}</RecipientID>
        <QuestionType>General</QuestionType>{media_xml}
    </MemberMessage>
</AddMemberMessageAAQToPartnerRequest>"""
    else:
        # 問い合わせのみ → RTQ (Response To Question)
        api_call = "AddMemberMessageRTQ"
        # 元メッセージIDを取得（DBから最新のinboundメッセージ）
        if not parent_message_id:
            try:
                from database.models import get_db, BuyerMessage
                db = get_db()
                last_msg = db.query(BuyerMessage).filter(
                    BuyerMessage.sender == recipient_id,
                    BuyerMessage.item_id == item_id,
                    BuyerMessage.direction == "inbound",
                ).order_by(BuyerMessage.received_at.desc()).first()
                if last_msg and last_msg.ebay_message_id:
                    parent_message_id = last_msg.ebay_message_id
                db.close()
            except Exception as e:
                logger.warning(f"親メッセージID取得エラー: {e}")

        parent_xml = f"<ParentMessageID>{parent_message_id}</ParentMessageID>" if parent_message_id else ""

        xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<AddMemberMessageRTQRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{token}</eBayAuthToken>
    </RequesterCredentials>
    <ItemID>{item_id}</ItemID>
    {parent_xml}
    <MemberMessage>
        {subject_xml}
        <Body>{_xml_escape(body)}</Body>
        <RecipientID>{_xml_escape(recipient_id)}</RecipientID>{media_xml}
    </MemberMessage>
</AddMemberMessageRTQRequest>"""

    headers = {
        "X-EBAY-API-SITEID": "0",
        "X-EBAY-API-COMPATIBILITY-LEVEL": "1349",
        "X-EBAY-API-CALL-NAME": api_call,
        "Content-Type": "text/xml",
    }

    logger.info(f"メッセージ送信: API={api_call}, to={recipient_id}, item={item_id}")

    resp = requests.post(
        f"{EBAY_API_BASE}/ws/api.dll",
        headers=headers,
        data=xml_body.encode("utf-8"),
        timeout=60,
    )

    ns_map = {"e": "urn:ebay:apis:eBLBaseComponents"}
    if resp.status_code != 200:
        logger.error(f"SendMessage failed: {resp.status_code}")
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    root = ET.fromstring(resp.text)
    ack = root.findtext("e:Ack", "", namespaces=ns_map)
    if ack in ("Success", "Warning"):
        logger.info(f"メッセージ送信成功: {recipient_id} (item={item_id}, api={api_call})")
        return {"success": True}
    else:
        errors = root.findall(".//e:Errors/e:ShortMessage", namespaces=ns_map)
        error_msg = errors[0].text if errors else "Unknown error"
        long_errors = root.findall(".//e:Errors/e:LongMessage", namespaces=ns_map)
        long_msg = long_errors[0].text if long_errors else ""
        logger.error(f"SendMessage error ({api_call}): {error_msg} — {long_msg}")

        # AAQToPartnerで失敗した場合、RTQにフォールバック
        if api_call == "AddMemberMessageAAQToPartner" and "partner" in (long_msg or error_msg).lower():
            logger.info("AAQToPartner失敗 → RTQにフォールバック")
            return send_buyer_message(
                item_id, recipient_id, body, subject, image_urls,
                parent_message_id=parent_message_id,
            )

        return {"success": False, "error": f"{error_msg}: {long_msg}" if long_msg else error_msg}


def mark_messages_read(message_ids: list[str], read: bool = True) -> dict:
    """Trading API (ReviseMyMessages) でメッセージの既読/未読を変更する。"""
    token = get_access_token()

    ids_xml = "\n".join(f"        <MessageID>{mid}</MessageID>" for mid in message_ids)

    xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<ReviseMyMessagesRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{token}</eBayAuthToken>
    </RequesterCredentials>
    <MessageIDs>
{ids_xml}
    </MessageIDs>
    <Read>{"true" if read else "false"}</Read>
</ReviseMyMessagesRequest>"""

    headers = {
        "X-EBAY-API-SITEID": "0",
        "X-EBAY-API-COMPATIBILITY-LEVEL": "1349",
        "X-EBAY-API-CALL-NAME": "ReviseMyMessages",
        "Content-Type": "text/xml",
    }

    resp = requests.post(
        f"{EBAY_API_BASE}/ws/api.dll",
        headers=headers,
        data=xml_body.encode("utf-8"),
        timeout=60,
    )

    ns_map = {"e": "urn:ebay:apis:eBLBaseComponents"}
    if resp.status_code != 200:
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    root = ET.fromstring(resp.text)
    ack = root.findtext("e:Ack", "", namespaces=ns_map)
    if ack in ("Success", "Warning"):
        logger.info(f"メッセージ既読更新: {len(message_ids)}件 → read={read}")
        return {"success": True, "count": len(message_ids)}
    return {"success": False, "error": "ReviseMyMessages failed"}


def upload_message_image(image_path: str) -> dict:
    """Trading API (UploadSiteHostedPictures) で画像をEPSにアップロードする。

    Returns:
        {"success": bool, "url": str | None, "error": str | None}
    """
    import base64
    token = get_access_token()

    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("ascii")

    # ファイル拡張子からMIMEタイプ推定
    ext = image_path.rsplit(".", 1)[-1].lower() if "." in image_path else "jpg"
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif"}
    mime_type = mime_map.get(ext, "image/jpeg")

    xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<UploadSiteHostedPicturesRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{token}</eBayAuthToken>
    </RequesterCredentials>
    <PictureName>{_xml_escape(image_path.rsplit("/", 1)[-1])}</PictureName>
    <PictureData>{image_data}</PictureData>
</UploadSiteHostedPicturesRequest>"""

    headers = {
        "X-EBAY-API-SITEID": "0",
        "X-EBAY-API-COMPATIBILITY-LEVEL": "1349",
        "X-EBAY-API-CALL-NAME": "UploadSiteHostedPictures",
        "Content-Type": "text/xml",
    }

    resp = requests.post(
        f"{EBAY_API_BASE}/ws/api.dll",
        headers=headers,
        data=xml_body.encode("utf-8"),
        timeout=120,
    )

    ns_map = {"e": "urn:ebay:apis:eBLBaseComponents"}
    if resp.status_code != 200:
        return {"success": False, "url": None, "error": f"HTTP {resp.status_code}"}

    root = ET.fromstring(resp.text)
    ack = root.findtext("e:Ack", "", namespaces=ns_map)
    if ack in ("Success", "Warning"):
        full_url = root.findtext(".//e:SiteHostedPictureDetails/e:FullURL", "", namespaces=ns_map)
        logger.info(f"画像アップロード成功: {full_url}")
        return {"success": True, "url": full_url}
    else:
        errors = root.findall(".//e:Errors/e:ShortMessage", namespaces=ns_map)
        error_msg = errors[0].text if errors else "Unknown error"
        return {"success": False, "url": None, "error": error_msg}


# ── Post-Order API (リターン・キャンセル) ────────────────

def get_return_requests(order_id: str = "", limit: int = 20) -> list:
    """Post-Order API でリターンリクエスト一覧を取得する。"""
    headers = _auth_headers()
    url = f"{EBAY_API_BASE}/post-order/v2/return/search"
    params = {"limit": str(limit), "sort": "RETURN_CREATION_DATE_DESC"}
    if order_id:
        params["order_id"] = order_id

    resp = requests.get(url, headers=headers, params=params, timeout=30)
    if resp.status_code != 200:
        logger.warning(f"Return search failed: {resp.status_code}")
        return []

    data = resp.json()
    returns = []
    for r in data.get("members", []):
        detail = r.get("returnRequest", r)
        returns.append({
            "return_id": detail.get("returnId", ""),
            "order_id": detail.get("orderId", ""),
            "item_id": detail.get("itemId", ""),
            "buyer": detail.get("buyerLoginName", ""),
            "reason": detail.get("returnReason", ""),
            "status": detail.get("currentStatus", detail.get("state", "")),
            "type": detail.get("returnType", ""),
            "created_date": detail.get("creationDate", {}).get("value", ""),
            "deadline": detail.get("sellerResponseDue", {}).get("value", ""),
            "refund_amount": detail.get("returnRefundAmount", {}).get("value", ""),
            "tracking_number": detail.get("returnShipment", {}).get("shipmentTrackingNumber", ""),
        })
    logger.info(f"リターンリクエスト: {len(returns)}件取得")
    return returns


def get_return_detail(return_id: str) -> dict:
    """特定のリターンリクエスト詳細を取得する。"""
    headers = _auth_headers()
    url = f"{EBAY_API_BASE}/post-order/v2/return/{return_id}"
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}"}
    return resp.json()


def get_cancellation_requests(order_id: str = "") -> list:
    """Post-Order API でキャンセルリクエスト一覧を取得する。"""
    headers = _auth_headers()
    url = f"{EBAY_API_BASE}/post-order/v2/cancellation/search"
    params = {"limit": "20", "sort": "CANCEL_REQUEST_DATE_DESC"}
    if order_id:
        params["order_id"] = order_id

    resp = requests.get(url, headers=headers, params=params, timeout=30)
    if resp.status_code != 200:
        logger.warning(f"Cancel search failed: {resp.status_code}")
        return []

    data = resp.json()
    cancels = []
    for c in data.get("cancellations", []):
        cancels.append({
            "cancel_id": c.get("cancelId", ""),
            "order_id": c.get("legacyOrderId", c.get("orderId", "")),
            "item_id": c.get("itemId", ""),
            "buyer": c.get("buyerLoginName", ""),
            "reason": c.get("cancelReason", ""),
            "status": c.get("cancelStatus", ""),
            "requested_date": c.get("requestedDate", ""),
        })
    return cancels


def respond_to_cancellation(cancel_id: str, accept: bool) -> dict:
    """キャンセルリクエストに Accept / Decline で応答する。"""
    headers = _auth_headers()
    action = "ACCEPT" if accept else "DECLINE"
    url = f"{EBAY_API_BASE}/post-order/v2/cancellation/{cancel_id}/{action.lower()}"

    resp = requests.post(url, headers=headers, timeout=15)
    if resp.status_code in (200, 204):
        logger.info(f"キャンセル{action}: {cancel_id}")
        return {"success": True, "action": action}
    else:
        error = resp.text[:300]
        logger.error(f"キャンセル応答失敗: {resp.status_code} {error}")
        return {"success": False, "error": error}


def get_best_offers(item_id: str) -> list[dict]:
    """Trading API (GetBestOffers) でアクティブなオファーを取得する。"""
    token = get_access_token()
    xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<GetBestOffersRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials><eBayAuthToken>{token}</eBayAuthToken></RequesterCredentials>
    <ItemID>{item_id}</ItemID>
    <BestOfferStatus>All</BestOfferStatus>
</GetBestOffersRequest>"""
    headers = {
        "X-EBAY-API-SITEID": "0",
        "X-EBAY-API-COMPATIBILITY-LEVEL": "1349",
        "X-EBAY-API-CALL-NAME": "GetBestOffers",
        "Content-Type": "text/xml",
    }
    resp = requests.post(f"{EBAY_API_BASE}/ws/api.dll", headers=headers, data=xml_body.encode("utf-8"), timeout=30)
    ns = {"e": "urn:ebay:apis:eBLBaseComponents"}
    offers = []
    try:
        root = ET.fromstring(resp.text)
        for offer in root.findall(".//e:BestOffer", ns):
            offer_id = offer.findtext("e:BestOfferID", "", ns)
            status = offer.findtext("e:Status", "", ns)
            price = offer.findtext(".//e:BestOfferPrice/e:Value", "0", ns)
            currency = offer.findtext(".//e:BestOfferPrice/e:CurrencyID", "USD", ns)
            quantity = offer.findtext("e:Quantity", "1", ns)
            buyer_id = offer.findtext(".//e:Buyer/e:UserID", "", ns)
            expiry = offer.findtext("e:ExpirationTime", "", ns)
            offers.append({
                "offer_id": offer_id,
                "status": status,
                "price": float(price),
                "currency": currency,
                "quantity": int(quantity),
                "buyer": buyer_id,
                "expires": expiry,
            })
    except Exception as e:
        logger.warning(f"GetBestOffers parse error: {e}")
    return offers


def respond_to_best_offer(
    item_id: str,
    offer_id: str,
    action: str,  # "Accept" | "Decline" | "Counter"
    counter_price: float = 0.0,
    counter_message: str = "",
) -> dict:
    """Trading API (RespondToBestOffer) でオファーに応答する。"""
    token = get_access_token()

    counter_xml = ""
    if action == "Counter" and counter_price > 0:
        counter_xml = f"""
    <RetractOffer>false</RetractOffer>
    <CounterOfferPrice>
        <Value>{counter_price:.2f}</Value>
        <CurrencyID>USD</CurrencyID>
    </CounterOfferPrice>"""
    msg_xml = f"<SellerResponse>{_xml_escape(counter_message)}</SellerResponse>" if counter_message else ""

    xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<RespondToBestOfferRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials><eBayAuthToken>{token}</eBayAuthToken></RequesterCredentials>
    <ItemID>{item_id}</ItemID>
    <BestOfferID>{offer_id}</BestOfferID>
    <Action>{action}</Action>
    {msg_xml}
    {counter_xml}
</RespondToBestOfferRequest>"""
    headers = {
        "X-EBAY-API-SITEID": "0",
        "X-EBAY-API-COMPATIBILITY-LEVEL": "1349",
        "X-EBAY-API-CALL-NAME": "RespondToBestOffer",
        "Content-Type": "text/xml",
    }
    resp = requests.post(f"{EBAY_API_BASE}/ws/api.dll", headers=headers, data=xml_body.encode("utf-8"), timeout=30)
    ns = {"e": "urn:ebay:apis:eBLBaseComponents"}
    try:
        root = ET.fromstring(resp.text)
        ack = root.findtext("e:Ack", "", ns)
        if ack in ("Success", "Warning"):
            logger.info(f"RespondToBestOffer成功: item={item_id} offer={offer_id} action={action}")
            return {"success": True, "action": action}
        errors = root.findall(".//e:Errors/e:ShortMessage", ns)
        error_msg = errors[0].text if errors else "Unknown error"
        logger.error(f"RespondToBestOffer失敗: {error_msg}")
        return {"success": False, "error": error_msg}
    except Exception as e:
        logger.error(f"RespondToBestOffer parse error: {e}")
        return {"success": False, "error": str(e)}


def accept_return_request(return_id: str) -> dict:
    """Post-Order API でリターンリクエストを承認する。"""
    headers = _auth_headers()
    url = f"{EBAY_API_BASE}/post-order/v2/return/{return_id}/decide"
    payload = {"decision": "SELLER_APPROVE"}
    resp = requests.post(url, headers=headers, json=payload, timeout=15)
    if resp.status_code in (200, 204):
        logger.info(f"リターン承認: {return_id}")
        return {"success": True}
    logger.error(f"リターン承認失敗: {resp.status_code} {resp.text[:200]}")
    return {"success": False, "error": resp.text[:200]}


def decline_return_request(return_id: str, reason: str = "NOT_RESPONSIBLE") -> dict:
    """Post-Order API でリターンリクエストを拒否する。"""
    headers = _auth_headers()
    url = f"{EBAY_API_BASE}/post-order/v2/return/{return_id}/decide"
    payload = {"decision": "SELLER_REJECT", "reason": reason}
    resp = requests.post(url, headers=headers, json=payload, timeout=15)
    if resp.status_code in (200, 204):
        logger.info(f"リターン拒否: {return_id}")
        return {"success": True}
    logger.error(f"リターン拒否失敗: {resp.status_code} {resp.text[:200]}")
    return {"success": False, "error": resp.text[:200]}


def _xml_escape(text: str) -> str:
    """XML特殊文字をエスケープ"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


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
            v.get("localizedValue", "")
            for v in aspect.get("aspectValues", [])[:20]
        ]
        entry = {"name": name, "values": values, "data_type": constraint.get("aspectDataType", "STRING")}

        if mode == "REQUIRED":
            required.append(entry)
        else:
            recommended.append(entry)

    logger.info(f"カテゴリ {category_id} Aspects: 必須{len(required)}件, 推奨{len(recommended)}件")
    return {"category_id": category_id, "required": required, "recommended": recommended}


# ── 新規出品 (Inventory API) ─────────────────────────────

def create_inventory_item(sku: str, product: dict, condition: str = "",
                          condition_description: str = "", quantity: int = 1) -> dict:
    """
    Sell Inventory API で新規 Inventory Item を作成する。

    product keys:
      title, description, aspects (dict), imageUrls (list[str])
    condition: Empty string = don't set (let eBay use category default)
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
    if condition and condition not in ("USED",):
        body["condition"] = condition
    elif condition == "USED":
        body["condition"] = "USED_VERY_GOOD"
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
        error = resp.text[:500]
        logger.error(f"Offer 公開失敗: {resp.status_code} {error}")
        return {"success": False, "error": error, "status_code": resp.status_code}


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
