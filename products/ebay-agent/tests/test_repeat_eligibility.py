"""compute_eligibility() のユニットテスト"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.models import Base, BuyerExclude, SalesRecord  # noqa: E402
from chat.repeat_engine import compute_eligibility  # noqa: E402


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _sale(**overrides) -> SalesRecord:
    now = datetime(2026, 5, 1, 12, 0, 0)
    base = dict(
        order_id="o-1",
        sku="SKU-1",
        title="Test",
        buyer_name="alice",
        sale_price_usd=120.0,
        progress="納品済み",
        sold_at=now - timedelta(days=20),
        delivered_at=now - timedelta(days=14),
        feedback_rating="Positive",
        feedback_received_at=now - timedelta(days=10),
        refund_status="",
        dispute_status="",
    )
    base.update(overrides)
    return SalesRecord(**base)


NOW = datetime(2026, 5, 1, 12, 0, 0)


def test_positive_feedback_after_d7_is_eligible(db):
    s = _sale()
    assert compute_eligibility(s, db, now=NOW) == 1


def test_refund_blocks_eligibility(db):
    s = _sale(refund_status="partial")
    assert compute_eligibility(s, db, now=NOW) == 0


def test_dispute_blocks_eligibility(db):
    s = _sale(dispute_status="inad")
    assert compute_eligibility(s, db, now=NOW) == 0


def test_cancelled_progress_blocks(db):
    s = _sale(progress="キャンセル")
    assert compute_eligibility(s, db, now=NOW) == 0


def test_silent_after_30d_is_eligible(db):
    s = _sale(
        feedback_rating="",
        feedback_received_at=None,
        delivered_at=NOW - timedelta(days=35),
    )
    assert compute_eligibility(s, db, now=NOW) == 1


def test_silent_after_only_15d_not_eligible(db):
    s = _sale(
        feedback_rating="",
        feedback_received_at=None,
        delivered_at=NOW - timedelta(days=15),
    )
    assert compute_eligibility(s, db, now=NOW) == 0


def test_negative_feedback_blocks(db):
    s = _sale(feedback_rating="Negative")
    assert compute_eligibility(s, db, now=NOW) == 0


def test_buyer_excluded(db):
    db.add(BuyerExclude(buyer_username="alice", reason="opt-out"))
    db.commit()
    s = _sale()
    assert compute_eligibility(s, db, now=NOW) == 0


def test_delivered_under_7d_not_eligible(db):
    s = _sale(delivered_at=NOW - timedelta(days=3))
    assert compute_eligibility(s, db, now=NOW) == 0


def test_not_shipped_yet_not_eligible(db):
    s = _sale(progress="注文済み", delivered_at=None)
    assert compute_eligibility(s, db, now=NOW) == 0
