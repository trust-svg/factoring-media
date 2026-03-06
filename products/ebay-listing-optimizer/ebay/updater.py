"""eBay Sell Inventory API で出品を更新"""
from __future__ import annotations

import json
import logging
from typing import Optional

import requests

from config import EBAY_API_BASE, EBAY_TITLE_MAX_LENGTH
from ebay.auth import get_auth_headers

logger = logging.getLogger(__name__)


async def update_listing(
    sku: str,
    title: str | None = None,
    description: str | None = None,
    item_specifics: dict[str, str] | None = None,
) -> bool:
    """
    eBay Sell Inventory API で出品を更新する。
    Inventory APIの仕様上、PUTで既存のinventory_itemを更新する。
    変更対象のフィールドのみ上書きするため、まず現在のデータを取得する。
    """
    headers = get_auth_headers()

    # 現在のinventory itemデータを取得
    url = f"{EBAY_API_BASE}/sell/inventory/v1/inventory_item/{sku}"
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code != 200:
        logger.error(f"SKU {sku} の取得失敗: {resp.status_code}")
        return False

    item_data = resp.json()
    product = item_data.get("product", {})

    # 更新対象フィールドを反映
    if title is not None:
        if len(title) > EBAY_TITLE_MAX_LENGTH:
            logger.error(f"タイトルが{EBAY_TITLE_MAX_LENGTH}文字を超えています: {len(title)}文字")
            return False
        product["title"] = title

    if description is not None:
        product["description"] = description

    if item_specifics is not None:
        aspects = product.get("aspects", {})
        for key, value in item_specifics.items():
            aspects[key] = [value] if isinstance(value, str) else value
        product["aspects"] = aspects

    item_data["product"] = product

    # PUTで更新
    resp = requests.put(url, headers=headers, json=item_data, timeout=15)
    if resp.status_code in (200, 204):
        logger.info(f"SKU {sku} を更新しました")
        return True
    else:
        logger.error(f"SKU {sku} の更新失敗: {resp.status_code} - {resp.text[:300]}")
        return False
