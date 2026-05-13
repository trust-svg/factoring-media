"""classify_sale() のジャンルルール判定テスト"""

from __future__ import annotations

import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.models import Base, ListingCategoryRule, SalesRecord  # noqa: E402
from chat.repeat_engine import classify_sale, seed_default_rules  # noqa: E402


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    seed_default_rules(session)
    yield session
    session.close()


def _sale(**overrides) -> SalesRecord:
    base = dict(
        order_id="o-1",
        sku="SKU-1",
        title="Generic item",
        buyer_name="alice",
        sale_price_usd=100.0,
    )
    base.update(overrides)
    return SalesRecord(**base)


def test_manual_override_wins(db):
    s = _sale(cost_note="some note [cat:audio_premium] more notes")
    assert classify_sale(db, s) == "audio_premium"


def test_figure_title_match(db):
    s = _sale(title="Bandai Gundam figure HG", sale_price_usd=80.0)
    assert classify_sale(db, s) == "figure_collectible"


def test_armor_title_match(db):
    s = _sale(title="Samurai armor display", sale_price_usd=900.0)
    assert classify_sale(db, s) == "armor_premium"


def test_fallback_other(db):
    s = _sale(title="Random unrelated thing", sale_price_usd=50.0)
    assert classify_sale(db, s) == "other"


def test_existing_tag_is_kept(db):
    s = _sale(title="Something", item_category_tag="watch_premium")
    assert classify_sale(db, s) == "watch_premium"


def test_seed_default_rules_idempotent(db):
    before = db.query(ListingCategoryRule).count()
    added = seed_default_rules(db)
    after = db.query(ListingCategoryRule).count()
    assert added == 0  # 既に seed されているので追加なし
    assert before == after
