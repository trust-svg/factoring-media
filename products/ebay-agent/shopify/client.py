"""Shopify Admin REST API ラッパー

レート制限: 2 req/秒（コール間に0.5秒スリープ）
APIバージョン: 2024-01
"""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

from config import SHOPIFY_ACCESS_TOKEN, SHOPIFY_SHOP_DOMAIN

logger = logging.getLogger("shopify.client")
_API_VERSION = "2024-01"


class ShopifyClient:
    def __init__(self) -> None:
        self._base = f"https://{SHOPIFY_SHOP_DOMAIN}/admin/api/{_API_VERSION}"
        self._headers = {
            "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
            "Content-Type": "application/json",
        }
        self._last_call_at: float = 0.0

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """レート制限付きリクエスト"""
        now = time.monotonic()
        wait = 0.5 - (now - self._last_call_at)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_call_at = time.monotonic()

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(
                method,
                f"{self._base}{path}",
                headers=self._headers,
                **kwargs,
            )
            resp.raise_for_status()
            return resp.json() if resp.content else {}

    async def create_product(
        self,
        sku: str,
        title: str,
        description_html: str,
        price_usd: float,
        image_urls: list[str],
    ) -> tuple[str, str]:
        """商品を作成し (product_id, variant_id) を返す。画像は最大3枚。"""
        images = [{"src": url} for url in image_urls[:3]]
        payload = {
            "product": {
                "title": title,
                "body_html": description_html,
                "status": "active",
                "variants": [{"price": f"{price_usd:.2f}", "sku": sku}],
                "images": images,
            }
        }
        data = await self._request("POST", "/products.json", json=payload)
        product = data["product"]
        return str(product["id"]), str(product["variants"][0]["id"])

    async def update_variant_price(self, variant_id: str, price_usd: float) -> None:
        """バリアントの価格を更新する"""
        payload = {"variant": {"price": f"{price_usd:.2f}"}}
        await self._request("PUT", f"/variants/{variant_id}.json", json=payload)

    async def delete_product(self, product_id: str) -> None:
        """商品を削除する（売れた・手動削除時に使用）"""
        await self._request("DELETE", f"/products/{product_id}.json")
