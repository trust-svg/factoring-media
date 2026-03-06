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
    url = f"{EBAY_API_BASE}/buy/browse/v1/item/{item_id}"
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code != 200:
        return None
    return resp.json()


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

        # バイヤー情報
        buyer_id = order_el.findtext(".//e:BuyerUserID", "", namespaces=ns_map)
        shipping_cost = order_el.findtext(
            ".//e:ShippingServiceSelected/e:ShippingServiceCost", "0", namespaces=ns_map
        )

        orders.append({
            "order_id": order_id,
            "total_usd": float(total_str),
            "created_time": created,
            "buyer_id": buyer_id,
            "shipping_cost_usd": float(shipping_cost),
            "items": items,
        })

    logger.info(f"GetOrders: {len(orders)}件の注文を取得")
    return orders


# ── バイヤーメッセージ (Trading API GetMyMessages) ────────

def get_buyer_messages(days: int = 7, limit: int = 20) -> list[dict]:
    """Trading API (GetMyMessages) でバイヤーメッセージを取得する。"""
    token = get_access_token()
    from_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00.000Z")

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

        messages.append({
            "message_id": msg_id,
            "sender": sender,
            "subject": subject,
            "body": body,
            "received_date": received,
            "is_read": is_read,
            "item_id": item_id,
            "responded": responded,
        })

    logger.info(f"GetMyMessages: {len(messages)}件のメッセージを取得")
    return messages


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
