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
