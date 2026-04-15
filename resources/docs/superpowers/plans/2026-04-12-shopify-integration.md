# Shopify Integration — ebay-agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** eBay出品をShopifyに自動同期（5%割引）し、どちらかで売れたら双方の在庫をリアルタイムで0にする。

**Architecture:** `shopify/` モジュールをebay-agentに追加。`client.py`がShopify Admin APIを叩き、`sync.py`が双方向同期ロジックを担う。Shopify webhookエンドポイントをFastAPIに追加。30分スケジューラーが定期的にeBay売上をチェックし、Shopify在庫を自動クローズ。4つの新Claudeツールで手動制御も可能。

**Tech Stack:** Shopify Admin REST API 2024-01、httpx（既存）、FastAPI、SQLAlchemy + SQLite、APScheduler

---

## ファイルマップ

| ファイル | 操作 | 責務 |
|---|---|---|
| `products/ebay-agent/config.py` | 修正 | Shopify設定値（ドメイン・トークン・Webhook秘密鍵・デフォルト割引率） |
| `products/ebay-agent/database/models.py` | 修正 | Listingに3カラム追加 + ShopifyConfigテーブル追加 + マイグレーション関数 |
| `products/ebay-agent/shopify/__init__.py` | 新規 | パッケージマーカー |
| `products/ebay-agent/shopify/client.py` | 新規 | Shopify Admin APIラッパー（レート制限付き） |
| `products/ebay-agent/shopify/sync.py` | 新規 | 双方向同期ロジック（push/close/価格計算） |
| `products/ebay-agent/main.py` | 修正 | webhookエンドポイント追加 + スケジューラーにジョブ追加 |
| `products/ebay-agent/comms/scheduled_jobs.py` | 修正 | `auto_sync_and_close_shopify` 関数追加 |
| `products/ebay-agent/tools/registry.py` | 修正 | 4つの新ツール定義追加 |
| `products/ebay-agent/tools/handlers.py` | 修正 | 4つの新ハンドラ + `_update_listing_handler`にShopify価格連動を追加 |
| `products/ebay-agent/test_shopify.py` | 新規 | 全Shopify機能のテスト（client/sync/webhook） |

---

## Task 1: Config + DB（基盤）

**Files:**
- Modify: `products/ebay-agent/config.py`
- Modify: `products/ebay-agent/database/models.py`
- Create: `products/ebay-agent/test_shopify.py`

- [ ] **Step 1: テストを書く（失敗確認用）**

```python
# products/ebay-agent/test_shopify.py
"""Shopify integration tests"""
import pytest
from database.models import ShopifyConfig, Listing


def test_shopify_config_table_exists(tmp_path):
    """ShopifyConfigテーブルがDBに作成されること"""
    import os
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/test.db"
    from database.models import init_db, engine
    init_db()
    from sqlalchemy import inspect
    inspector = inspect(engine)
    assert "shopify_config" in inspector.get_table_names()


def test_listing_has_shopify_columns(tmp_path):
    """Listingテーブルにshopify_product_idカラムが存在すること"""
    import os
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/test2.db"
    from database.models import init_db, engine
    init_db()
    from sqlalchemy import inspect, text
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(listings)"))
        columns = {row[1] for row in result.fetchall()}
    assert "shopify_product_id" in columns
    assert "shopify_variant_id" in columns
    assert "shopify_synced_at" in columns
```

- [ ] **Step 2: テストを実行して失敗を確認**

```bash
cd products/ebay-agent
python -m pytest test_shopify.py::test_shopify_config_table_exists -v
```

Expected: `FAILED` (ShopifyConfig not defined)

- [ ] **Step 3: config.pyにShopify設定値を追加**

`products/ebay-agent/config.py` の末尾に追加:

```python
# ── Shopify ───────────────────────────────────────────────
SHOPIFY_SHOP_DOMAIN = os.getenv("SHOPIFY_SHOP_DOMAIN", "")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
SHOPIFY_WEBHOOK_SECRET = os.getenv("SHOPIFY_WEBHOOK_SECRET", "")
SHOPIFY_DISCOUNT_RATE = float(os.getenv("SHOPIFY_DISCOUNT_RATE", "0.05"))
```

- [ ] **Step 4: models.pyにShopifyConfigテーブルとListingカラムを追加**

`products/ebay-agent/database/models.py` の `Listing` クラスに3カラム追加（`fetched_at` の直後）:

```python
    shopify_product_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    shopify_variant_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    shopify_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
```

`InventoryItem` クラスの後に `ShopifyConfig` クラスを追加:

```python
class ShopifyConfig(Base):
    """Shopify設定（discount_rate等をDB管理）"""
    __tablename__ = "shopify_config"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 5: `init_db()`にマイグレーション関数を追加**

`models.py` の `init_db()` 関数を以下に置き換え（既存のcreate_allはそのまま残す）:

```python
def _migrate_shopify_columns(engine_instance) -> None:
    """既存のlistingsテーブルにShopifyカラムを追加（冪等）"""
    from sqlalchemy import text
    with engine_instance.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(listings)"))
        existing = {row[1] for row in result.fetchall()}
        stmts = []
        if "shopify_product_id" not in existing:
            stmts.append("ALTER TABLE listings ADD COLUMN shopify_product_id TEXT")
        if "shopify_variant_id" not in existing:
            stmts.append("ALTER TABLE listings ADD COLUMN shopify_variant_id TEXT")
        if "shopify_synced_at" not in existing:
            stmts.append("ALTER TABLE listings ADD COLUMN shopify_synced_at DATETIME")
        for stmt in stmts:
            conn.execute(text(stmt))
        if stmts:
            conn.commit()
```

既存の `init_db()` 関数内の `Base.metadata.create_all(engine)` の直後に呼び出しを追加:

```python
    _migrate_shopify_columns(engine)
```

- [ ] **Step 6: テストを実行してパスを確認**

```bash
cd products/ebay-agent
python -m pytest test_shopify.py -v
```

Expected: `PASSED PASSED`

- [ ] **Step 7: コミット**

```bash
cd products/ebay-agent
git add config.py database/models.py test_shopify.py
git commit -m "feat(shopify): add config vars, ShopifyConfig table, and Listing columns"
```

---

## Task 2: ShopifyClient（APIラッパー）

**Files:**
- Create: `products/ebay-agent/shopify/__init__.py`
- Create: `products/ebay-agent/shopify/client.py`
- Modify: `products/ebay-agent/test_shopify.py`

- [ ] **Step 1: テストを追加**

`test_shopify.py` に追加:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_create_product_returns_product_and_variant_ids():
    """create_product が (product_id, variant_id) のタプルを返すこと"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "product": {
            "id": 123456,
            "variants": [{"id": 789012, "sku": "TEST-001"}],
        }
    }
    mock_resp.content = b"..."
    mock_resp.raise_for_status = MagicMock()

    with patch("shopify.client.httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(request=AsyncMock(return_value=mock_resp))
        )
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        from shopify.client import ShopifyClient
        client = ShopifyClient()
        product_id, variant_id = await client.create_product(
            sku="TEST-001",
            title="Test Product",
            description_html="<p>Test</p>",
            price_usd=94.99,
            image_urls=["https://example.com/img.jpg"],
        )

    assert product_id == "123456"
    assert variant_id == "789012"


@pytest.mark.asyncio
async def test_delete_product_calls_delete_endpoint():
    """delete_product がDELETEリクエストを送ること"""
    mock_resp = MagicMock()
    mock_resp.content = b""
    mock_resp.raise_for_status = MagicMock()

    with patch("shopify.client.httpx.AsyncClient") as MockClient:
        mock_http = MagicMock()
        mock_http.request = AsyncMock(return_value=mock_resp)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        from shopify.client import ShopifyClient
        client = ShopifyClient()
        await client.delete_product("123456")

    call_args = mock_http.request.call_args
    assert call_args[0][0] == "DELETE"
    assert "123456" in call_args[0][1]
```

- [ ] **Step 2: テストを実行して失敗を確認**

```bash
cd products/ebay-agent
python -m pytest test_shopify.py::test_create_product_returns_product_and_variant_ids -v
```

Expected: `FAILED` (shopify.client not found)

- [ ] **Step 3: `shopify/__init__.py` を作成**

```python
# products/ebay-agent/shopify/__init__.py
```

（空ファイル）

- [ ] **Step 4: `shopify/client.py` を作成**

```python
"""Shopify Admin REST API ラッパー

レート制限: 2 req/秒（コール間に0.5秒スリープ）
APIバージョン: 2024-01
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

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
```

- [ ] **Step 5: pytest-asyncioを追加（未インストールの場合）**

```bash
cd products/ebay-agent
pip install pytest-asyncio
```

`test_shopify.py` の先頭に追加:

```python
import pytest
# pytest-asyncio の自動モード設定
pytestmark = pytest.mark.asyncio
```

また `pytest.ini` または `pyproject.toml` がない場合は、プロジェクトルートに以下を作成:

```ini
# products/ebay-agent/pytest.ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 6: テストを実行してパスを確認**

```bash
cd products/ebay-agent
python -m pytest test_shopify.py::test_create_product_returns_product_and_variant_ids test_shopify.py::test_delete_product_calls_delete_endpoint -v
```

Expected: `PASSED PASSED`

- [ ] **Step 7: コミット**

```bash
git add shopify/__init__.py shopify/client.py test_shopify.py pytest.ini
git commit -m "feat(shopify): add ShopifyClient with rate-limited Admin API wrapper"
```

---

## Task 3: 同期ロジック（sync.py）

**Files:**
- Create: `products/ebay-agent/shopify/sync.py`
- Modify: `products/ebay-agent/test_shopify.py`

- [ ] **Step 1: テストを追加**

`test_shopify.py` に追加:

```python
from shopify.sync import get_shopify_price, get_discount_rate


def test_get_shopify_price_basic():
    assert get_shopify_price(100.0, 0.05) == 95.0


def test_get_shopify_price_rounding():
    # 端数は2桁で丸める
    assert get_shopify_price(33.33, 0.05) == 31.66


def test_get_shopify_price_zero_discount():
    assert get_shopify_price(99.99, 0.0) == 99.99


def test_get_discount_rate_default(tmp_path):
    """DBにレコードがない場合はconfig.pyのデフォルト値を返すこと"""
    import os
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/test3.db"
    os.environ["SHOPIFY_DISCOUNT_RATE"] = "0.05"
    from database.models import init_db, get_db
    init_db()
    db = get_db()
    try:
        rate = get_discount_rate(db)
        assert rate == 0.05
    finally:
        db.close()


def test_get_discount_rate_from_db(tmp_path):
    """DBにレコードがある場合はDB値を優先すること"""
    import os
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/test4.db"
    from database.models import init_db, get_db, ShopifyConfig
    from datetime import datetime
    init_db()
    db = get_db()
    db.add(ShopifyConfig(key="discount_rate", value="0.03", updated_at=datetime.utcnow()))
    db.commit()
    rate = get_discount_rate(db)
    db.close()
    assert rate == 0.03
```

- [ ] **Step 2: テストを実行して失敗を確認**

```bash
cd products/ebay-agent
python -m pytest test_shopify.py::test_get_shopify_price_basic -v
```

Expected: `FAILED` (shopify.sync not found)

- [ ] **Step 3: `shopify/sync.py` を作成**

```python
"""Shopify 双方向同期ロジック

- push_listing_to_shopify: 1件をShopifyに同期
- push_all_unsynced: 未同期の全出品を一括同期
- close_shopify_for_sold_items: eBayで売れた商品をShopifyから削除
- get_shopify_price: eBay価格 → Shopify割引価格
- get_discount_rate: 現在の割引率をDB/configから取得
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from config import SHOPIFY_DISCOUNT_RATE
from database.models import get_db, Listing, ShopifyConfig
from shopify.client import ShopifyClient

logger = logging.getLogger("shopify.sync")


def get_discount_rate(db: Session) -> float:
    """割引率をShopifyConfigテーブルから取得。なければenv変数のデフォルト値。"""
    config = db.query(ShopifyConfig).filter_by(key="discount_rate").first()
    if config:
        return float(config.value)
    return SHOPIFY_DISCOUNT_RATE


def get_shopify_price(ebay_price_usd: float, discount_rate: float) -> float:
    """eBay価格に割引率を適用して2桁に丸める"""
    return round(ebay_price_usd * (1 - discount_rate), 2)


async def push_listing_to_shopify(sku: str) -> None:
    """1件のeBay出品をShopifyに同期する（すでに同期済みならスキップ）"""
    client = ShopifyClient()
    db = get_db()
    try:
        listing = db.query(Listing).filter_by(sku=sku).first()
        if not listing:
            logger.warning(f"SKU {sku} not found in DB")
            return
        if listing.shopify_product_id:
            logger.debug(f"SKU {sku} already synced to Shopify")
            return

        discount_rate = get_discount_rate(db)
        shopify_price = get_shopify_price(listing.price_usd, discount_rate)
        image_urls = json.loads(listing.image_urls_json or "[]")

        product_id, variant_id = await client.create_product(
            sku=listing.sku,
            title=listing.title,
            description_html=listing.description or "",
            price_usd=shopify_price,
            image_urls=image_urls,
        )

        listing.shopify_product_id = product_id
        listing.shopify_variant_id = variant_id
        listing.shopify_synced_at = datetime.utcnow()
        db.commit()
        logger.info(f"Pushed {sku} to Shopify (product_id={product_id})")

    except Exception:
        db.rollback()
        logger.exception(f"Failed to push {sku} to Shopify")
    finally:
        db.close()


async def push_all_unsynced() -> dict[str, int]:
    """shopify_product_idがNullで在庫>0の全ListingをShopifyに同期する"""
    db = get_db()
    try:
        listings = (
            db.query(Listing)
            .filter(Listing.shopify_product_id.is_(None), Listing.quantity > 0)
            .all()
        )
        skus = [l.sku for l in listings]
    finally:
        db.close()

    success, failed = 0, 0
    for sku in skus:
        try:
            await push_listing_to_shopify(sku)
            success += 1
        except Exception:
            failed += 1
            logger.exception(f"push_all_unsynced: failed for {sku}")

    logger.info(f"push_all_unsynced: success={success}, failed={failed}")
    return {"success": success, "failed": failed}


async def close_shopify_for_sold_items() -> int:
    """eBayで売れた（quantity=0）商品をShopifyから削除する"""
    client = ShopifyClient()
    db = get_db()
    try:
        sold = (
            db.query(Listing)
            .filter(Listing.quantity == 0, Listing.shopify_product_id.isnot(None))
            .all()
        )
        count = 0
        for listing in sold:
            try:
                await client.delete_product(listing.shopify_product_id)
                listing.shopify_product_id = None
                listing.shopify_variant_id = None
                db.commit()
                count += 1
                logger.info(f"Closed Shopify product for sold SKU {listing.sku}")
            except Exception:
                logger.exception(f"Failed to close Shopify for {listing.sku}")
        return count
    finally:
        db.close()
```

- [ ] **Step 4: テストを実行してパスを確認**

```bash
cd products/ebay-agent
python -m pytest test_shopify.py::test_get_shopify_price_basic test_shopify.py::test_get_shopify_price_rounding test_shopify.py::test_get_shopify_price_zero_discount test_shopify.py::test_get_discount_rate_default test_shopify.py::test_get_discount_rate_from_db -v
```

Expected: 5 PASSED

- [ ] **Step 5: コミット**

```bash
git add shopify/sync.py test_shopify.py
git commit -m "feat(shopify): add sync logic — push/close/price calculation"
```

---

## Task 4: Webhookエンドポイント

**Files:**
- Modify: `products/ebay-agent/main.py`
- Modify: `products/ebay-agent/test_shopify.py`

- [ ] **Step 1: テストを追加**

`test_shopify.py` に追加:

```python
import hashlib
import hmac
import base64


def _make_shopify_signature(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def test_verify_shopify_webhook_valid():
    """正しい署名はTrueを返すこと"""
    from main import verify_shopify_webhook
    body = b'{"test": "data"}'
    secret = "test_secret_123"
    sig = _make_shopify_signature(body, secret)
    assert verify_shopify_webhook(body, sig, secret) is True


def test_verify_shopify_webhook_invalid():
    """不正な署名はFalseを返すこと"""
    from main import verify_shopify_webhook
    body = b'{"test": "data"}'
    assert verify_shopify_webhook(body, "invalid_sig", "test_secret_123") is False
```

- [ ] **Step 2: テストを実行して失敗を確認**

```bash
cd products/ebay-agent
python -m pytest test_shopify.py::test_verify_shopify_webhook_valid -v
```

Expected: `FAILED` (verify_shopify_webhook not found in main)

- [ ] **Step 3: `main.py` にverify関数とwebhookエンドポイントを追加**

`main.py` のimport部分に追加:

```python
import hashlib
import hmac
import base64
from config import SHOPIFY_WEBHOOK_SECRET
```

`main.py` のルート定義部分（他のエンドポイントの近く）に追加:

```python
def verify_shopify_webhook(body: bytes, signature: str, secret: str) -> bool:
    """Shopify webhookのHMAC-SHA256署名を検証する"""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    computed = base64.b64encode(digest).decode()
    return hmac.compare_digest(computed, signature)


@app.post("/shopify/webhook/order-created")
async def shopify_order_created(request: Request):
    """Shopifyで注文が発生したとき — 対応するeBay在庫とShopify商品を閉じる"""
    body = await request.body()
    signature = request.headers.get("X-Shopify-Hmac-Sha256", "")

    if not verify_shopify_webhook(body, signature, SHOPIFY_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid Shopify webhook signature")

    payload = json.loads(body)
    line_items = payload.get("line_items", [])

    db = get_db()
    try:
        for item in line_items:
            sku = item.get("sku", "")
            if not sku:
                continue
            listing = db.query(Listing).filter_by(sku=sku).first()
            if not listing:
                continue
            # eBay在庫を0に
            listing.quantity = 0
            # Shopify商品も削除
            if listing.shopify_product_id:
                from shopify.client import ShopifyClient
                client = ShopifyClient()
                try:
                    await client.delete_product(listing.shopify_product_id)
                except Exception:
                    logger.warning(f"Failed to delete Shopify product for {sku}")
                listing.shopify_product_id = None
                listing.shopify_variant_id = None
            db.commit()
            logger.info(f"Webhook: closed eBay+Shopify for sold SKU {sku}")
    finally:
        db.close()

    return {"status": "ok"}
```

- [ ] **Step 4: テストを実行してパスを確認**

```bash
cd products/ebay-agent
python -m pytest test_shopify.py::test_verify_shopify_webhook_valid test_shopify.py::test_verify_shopify_webhook_invalid -v
```

Expected: 2 PASSED

- [ ] **Step 5: コミット**

```bash
git add main.py test_shopify.py
git commit -m "feat(shopify): add webhook endpoint POST /shopify/webhook/order-created"
```

---

## Task 5: スケジューラー統合

**Files:**
- Modify: `products/ebay-agent/comms/scheduled_jobs.py`
- Modify: `products/ebay-agent/main.py`

- [ ] **Step 1: `comms/scheduled_jobs.py` に `auto_sync_and_close_shopify` を追加**

ファイル末尾に追加:

```python
def auto_sync_and_close_shopify() -> None:
    """30分ごとに実行: 未同期出品のShopify同期 + 売れた商品のShopify削除"""
    import asyncio
    from shopify.sync import push_all_unsynced, close_shopify_for_sold_items

    logger.info("Starting Shopify sync job...")
    try:
        result = asyncio.run(push_all_unsynced())
        logger.info(f"Shopify push: success={result['success']}, failed={result['failed']}")
    except Exception:
        logger.exception("push_all_unsynced failed")

    try:
        closed = asyncio.run(close_shopify_for_sold_items())
        logger.info(f"Shopify close: {closed} products closed")
    except Exception:
        logger.exception("close_shopify_for_sold_items failed")
```

- [ ] **Step 2: `main.py` の `_start_scheduler()` にジョブを追加**

`_start_scheduler()` 内の既存 `scheduler.add_job(...)` 呼び出しの後に追加:

```python
        # Shopify同期（30分間隔）: 未同期出品のpush + 売れた商品のclose
        scheduler.add_job(
            auto_sync_and_close_shopify,
            "interval",
            minutes=30,
            id="shopify_sync",
            name="Shopify在庫同期",
        )
```

`main.py` の `_start_scheduler()` のimport行（`from comms.scheduled_jobs import ...`）に `auto_sync_and_close_shopify` を追加:

```python
        from comms.scheduled_jobs import send_morning_digest, send_weekly_report, auto_sync_sales, auto_sync_and_close_shopify
```

- [ ] **Step 3: 手動でジョブが動くかを確認**

```bash
cd products/ebay-agent
python -c "
from comms.scheduled_jobs import auto_sync_and_close_shopify
print('Running auto_sync_and_close_shopify...')
auto_sync_and_close_shopify()
print('Done')
"
```

Expected: エラーなく完了（Shopify credentialsが未設定の場合はAPI errorのログが出るが正常終了すること）

- [ ] **Step 4: コミット**

```bash
git add comms/scheduled_jobs.py main.py
git commit -m "feat(shopify): add 30-minute scheduler job for bidirectional sync"
```

---

## Task 6: 新Claudeツール（registry + handlers）

**Files:**
- Modify: `products/ebay-agent/tools/registry.py`
- Modify: `products/ebay-agent/tools/handlers.py`
- Modify: `products/ebay-agent/test_shopify.py`

- [ ] **Step 1: テストを追加**

`test_shopify.py` に追加:

```python
def test_get_shopify_price_tool_in_registry():
    """新しい4ツールがAGENT_TOOLSに登録されていること"""
    from tools.registry import AGENT_TOOLS
    names = {t["name"] for t in AGENT_TOOLS}
    assert "sync_all_to_shopify" in names
    assert "set_shopify_discount" in names
    assert "get_shopify_status" in names
    assert "remove_from_shopify" in names
```

- [ ] **Step 2: テストを実行して失敗を確認**

```bash
cd products/ebay-agent
python -m pytest test_shopify.py::test_get_shopify_price_tool_in_registry -v
```

Expected: `FAILED`

- [ ] **Step 3: `tools/registry.py` に4ツールを追加**

`AGENT_TOOLS` リストの末尾（`]` の前）に追加:

```python
    # ── Shopify連携 ──
    {
        "name": "sync_all_to_shopify",
        "description": "未同期のeBay出品を一括でShopifyストアに同期する。新しく出品した後に実行すると自動的に商品が追加される。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "set_shopify_discount",
        "description": "Shopifyの割引率を変更する。例: 0.05 = 5%引き、0.03 = 3%引き。変更後すぐ有効。",
        "input_schema": {
            "type": "object",
            "properties": {
                "discount_rate": {
                    "type": "number",
                    "description": "割引率（0〜1の小数。例: 0.05 = 5%割引）",
                },
            },
            "required": ["discount_rate"],
        },
    },
    {
        "name": "get_shopify_status",
        "description": "Shopify同期状況を確認する。同期済み件数・未同期件数・現在の割引率を返す。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "remove_from_shopify",
        "description": "特定SKUをShopifyから削除する。eBay出品は残る。[破壊的操作]",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku": {
                    "type": "string",
                    "description": "Shopifyから削除するSKU",
                },
            },
            "required": ["sku"],
        },
    },
```

`DESTRUCTIVE_TOOLS` セットに `"remove_from_shopify"` を追加:

```python
DESTRUCTIVE_TOOLS = {"update_listing", "apply_price_change", "publish_instagram_post", "publish_draft_listings", "remove_from_shopify"}
```

- [ ] **Step 4: `tools/handlers.py` に4ハンドラを追加**

まずimport部に追加（ファイル先頭のimport群に）:

```python
from datetime import datetime
from database.models import ShopifyConfig
from shopify.sync import get_discount_rate, get_shopify_price
```

ファイル末尾の `HANDLERS` dictの直前に4ハンドラ関数を追加:

```python
async def _sync_all_to_shopify(params: dict) -> dict:
    from shopify.sync import push_all_unsynced
    result = await push_all_unsynced()
    return {
        "message": f"Shopify同期完了: 成功 {result['success']}件、失敗 {result['failed']}件",
        **result,
    }


async def _set_shopify_discount(params: dict) -> dict:
    discount_rate = float(params["discount_rate"])
    if not (0.0 <= discount_rate <= 1.0):
        return {"error": "discount_rate は0〜1の範囲で指定してください"}
    db = get_db()
    try:
        config = db.query(ShopifyConfig).filter_by(key="discount_rate").first()
        if config:
            config.value = str(discount_rate)
            config.updated_at = datetime.utcnow()
        else:
            db.add(ShopifyConfig(key="discount_rate", value=str(discount_rate), updated_at=datetime.utcnow()))
        db.commit()
        return {"message": f"Shopify割引率を {discount_rate*100:.1f}% に変更しました", "discount_rate": discount_rate}
    finally:
        db.close()


async def _get_shopify_status(params: dict) -> dict:
    from database.models import Listing
    db = get_db()
    try:
        synced = db.query(Listing).filter(Listing.shopify_product_id.isnot(None)).count()
        unsynced = db.query(Listing).filter(
            Listing.shopify_product_id.is_(None),
            Listing.quantity > 0,
        ).count()
        discount_rate = get_discount_rate(db)
        return {
            "synced": synced,
            "unsynced": unsynced,
            "discount_rate": discount_rate,
            "discount_pct": f"{discount_rate*100:.1f}%",
        }
    finally:
        db.close()


async def _remove_from_shopify(params: dict) -> dict:
    sku = params["sku"]
    from database.models import Listing
    from shopify.client import ShopifyClient
    db = get_db()
    try:
        listing = db.query(Listing).filter_by(sku=sku).first()
        if not listing:
            return {"error": f"SKU {sku} が見つかりません"}
        if not listing.shopify_product_id:
            return {"error": f"SKU {sku} はShopifyに同期されていません"}
        client = ShopifyClient()
        await client.delete_product(listing.shopify_product_id)
        listing.shopify_product_id = None
        listing.shopify_variant_id = None
        db.commit()
        return {"message": f"SKU {sku} をShopifyから削除しました"}
    finally:
        db.close()
```

`HANDLERS` dictに4エントリを追加（既存の末尾 `}` の前）:

```python
    "sync_all_to_shopify": _sync_all_to_shopify,
    "set_shopify_discount": _set_shopify_discount,
    "get_shopify_status": _get_shopify_status,
    "remove_from_shopify": _remove_from_shopify,
```

- [ ] **Step 5: テストを実行してパスを確認**

```bash
cd products/ebay-agent
python -m pytest test_shopify.py::test_get_shopify_price_tool_in_registry -v
```

Expected: `PASSED`

- [ ] **Step 6: コミット**

```bash
git add tools/registry.py tools/handlers.py test_shopify.py
git commit -m "feat(shopify): add 4 Claude tools — sync/discount/status/remove"
```

---

## Task 7: `update_listing` Shopify価格連動

**Files:**
- Modify: `products/ebay-agent/tools/handlers.py`
- Modify: `products/ebay-agent/test_shopify.py`

- [ ] **Step 1: テストを追加**

`test_shopify.py` に追加:

```python
@pytest.mark.asyncio
async def test_update_listing_syncs_shopify_price():
    """update_listingでprice_usdを変更したとき、Shopify側の価格も更新されること"""
    update_variant_calls = []

    async def mock_update_variant(variant_id, price_usd):
        update_variant_calls.append({"variant_id": variant_id, "price_usd": price_usd})

    # DB lookupをmock: shopify_variant_idが設定されたListingを返す
    mock_listing = MagicMock()
    mock_listing.shopify_variant_id = "888"

    mock_db = MagicMock()
    mock_db.query.return_value.filter_by.return_value.first.return_value = mock_listing
    mock_db.close = MagicMock()

    mock_client = MagicMock()
    mock_client.update_variant_price = AsyncMock(side_effect=mock_update_variant)

    with patch("tools.handlers.get_db", return_value=mock_db), \
         patch("tools.handlers.ebay_update_listing", return_value={"success": True, "changes": []}), \
         patch("shopify.client.ShopifyClient", return_value=mock_client), \
         patch("tools.handlers.get_discount_rate", return_value=0.05):
        from tools.handlers import _update_listing_handler
        await _update_listing_handler({"sku": "TEST-SYNC-001", "price_usd": 120.0})

    assert len(update_variant_calls) == 1
    # Shopify価格 = 120.0 * (1 - 0.05) = 114.0
    assert update_variant_calls[0]["price_usd"] == 114.0
    assert update_variant_calls[0]["variant_id"] == "888"
```

- [ ] **Step 2: テストを実行して失敗を確認**

```bash
cd products/ebay-agent
python -m pytest test_shopify.py::test_update_listing_syncs_shopify_price -v
```

Expected: `FAILED`

- [ ] **Step 3: `_update_listing_handler` にShopify価格連動を追加**

`products/ebay-agent/tools/handlers.py` の `_update_listing_handler` 関数（`result = ebay_update_listing(sku, updates)` の後）を以下に修正:

既存コード（result = ebay_update_listing行の後）:
```python
    result = ebay_update_listing(sku, updates)

    # 変更履歴を記録
    if result["success"]:
```

↓ 以下に置き換え:

```python
    result = ebay_update_listing(sku, updates)

    # Shopify価格を連動更新（price_usdが変更された場合のみ）
    if result["success"] and "price_usd" in params:
        new_price = params["price_usd"]
        db_check = get_db()
        try:
            from database.models import Listing
            listing_obj = db_check.query(Listing).filter_by(sku=sku).first()
            if listing_obj and listing_obj.shopify_variant_id:
                discount_rate = get_discount_rate(db_check)
                shopify_price = get_shopify_price(new_price, discount_rate)
                try:
                    from shopify.client import ShopifyClient
                    client = ShopifyClient()
                    await client.update_variant_price(listing_obj.shopify_variant_id, shopify_price)
                    logger.info(f"Synced Shopify price for {sku}: ${shopify_price:.2f}")
                except Exception:
                    logger.warning(f"Failed to sync Shopify price for {sku}")
        finally:
            db_check.close()

    # 変更履歴を記録
    if result["success"]:
```

- [ ] **Step 4: テストを実行してパスを確認**

```bash
cd products/ebay-agent
python -m pytest test_shopify.py::test_update_listing_syncs_shopify_price -v
```

Expected: `PASSED`

- [ ] **Step 5: 全テストをまとめて実行**

```bash
cd products/ebay-agent
python -m pytest test_shopify.py -v
```

Expected: 全テスト PASSED

- [ ] **Step 6: コミット**

```bash
git add tools/handlers.py test_shopify.py
git commit -m "feat(shopify): sync Shopify price when eBay price is updated via update_listing"
```

---

## セットアップメモ（Shopify側の手動作業）

実装完了後に必要な手動セットアップ:

1. Shopify Basic プラン契約（$29/月）
2. Admin API → `Custom apps` → アクセストークン発行（スコープ: `write_products`, `read_orders`, `write_inventory`）
3. `.env` に `SHOPIFY_SHOP_DOMAIN` / `SHOPIFY_ACCESS_TOKEN` / `SHOPIFY_WEBHOOK_SECRET` を追加
4. Shopify管理画面 → 通知 → webhookを登録:
   - イベント: `注文/作成`
   - URL: `https://ebay.trustlink-tk.com/shopify/webhook/order-created`
5. Shopify管理画面 → 送料設定（国際送料プロファイルを手動設定）
6. `sync_all_to_shopify` ツールを実行して既存eBay出品を一括同期

---

## スペックカバレッジ確認

| 要件 | タスク |
|---|---|
| Shopify設定値（ドメイン・トークン等） | Task 1 |
| Listingにshopify_product_id/variant_idカラム追加 | Task 1 |
| ShopifyConfigテーブル（discount_rate管理） | Task 1 |
| ShopifyClient（create/update/delete） | Task 2 |
| 0.5秒スロットリング | Task 2 |
| eBay画像をShopifyにホスト（最大3枚） | Task 2 |
| push_listing_to_shopify（未同期のみ） | Task 3 |
| push_all_unsynced（一括同期） | Task 3 |
| close_shopify_for_sold_items（eBay売れ→削除） | Task 3 |
| get_shopify_price（割引計算） | Task 3 |
| get_discount_rate（DB優先） | Task 3 |
| webhook HMAC検証 | Task 4 |
| Shopify売れ→eBay在庫0+Shopify削除 | Task 4 |
| 30分スケジューラー | Task 5 |
| sync_all_to_shopify ツール | Task 6 |
| set_shopify_discount ツール | Task 6 |
| get_shopify_status ツール | Task 6 |
| remove_from_shopify ツール | Task 6 |
| update_listing価格変更→Shopify価格連動 | Task 7 |
