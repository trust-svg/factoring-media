# products/ebay-agent/test_shopify.py
"""Shopify integration tests"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_test_engine(tmp_path, db_name="test.db"):
    """テスト用のインメモリではないSQLiteエンジンを作成する（シングルトン問題を回避）"""
    from sqlalchemy import create_engine as _ce
    from database.models import Base, _migrate_shopify_columns
    url = f"sqlite:///{tmp_path}/{db_name}"
    engine = _ce(url)
    Base.metadata.create_all(engine)
    _migrate_shopify_columns(engine)
    return engine


def test_shopify_config_table_exists(tmp_path):
    """ShopifyConfigテーブルがDBに作成されること"""
    from sqlalchemy import inspect
    engine = _make_test_engine(tmp_path, "test.db")
    inspector = inspect(engine)
    assert "shopify_config" in inspector.get_table_names()


def test_listing_has_shopify_columns(tmp_path):
    """Listingテーブルにshopify_product_idカラムが存在すること"""
    from sqlalchemy import text
    engine = _make_test_engine(tmp_path, "test2.db")
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(listings)"))
        columns = {row[1] for row in result.fetchall()}
    assert "shopify_product_id" in columns
    assert "shopify_variant_id" in columns
    assert "shopify_synced_at" in columns


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
