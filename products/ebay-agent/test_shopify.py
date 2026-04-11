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
