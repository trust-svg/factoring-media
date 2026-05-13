"""Telegram callback_data の parse + handle_telegram_action 遷移テスト"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import models as _models  # noqa: E402
from database.models import Base, OutboundOffer  # noqa: E402
from comms.telegram_approval import parse_callback_query  # noqa: E402


# ── parse_callback_query ────────────────────────────────


def test_parse_valid_callback():
    update = {
        "callback_query": {
            "id": "abc",
            "from": {"id": 1, "username": "hiro"},
            "message": {"message_id": 42, "chat": {"id": 100}},
            "data": "ro:approve:99",
        }
    }
    parsed = parse_callback_query(update)
    assert parsed["action"] == "approve"
    assert parsed["offer_id"] == 99
    assert parsed["callback_query_id"] == "abc"


def test_parse_invalid_prefix():
    update = {"callback_query": {"data": "other:approve:99"}}
    assert parse_callback_query(update) is None


def test_parse_malformed_id():
    update = {"callback_query": {"data": "ro:approve:not_int"}}
    assert parse_callback_query(update) is None


def test_parse_no_callback():
    update = {"message": {"text": "hi"}}
    assert parse_callback_query(update) is None


# ── handle_telegram_action 状態遷移 ────────────────────


@pytest.fixture
def isolated_db(monkeypatch):
    """SessionLocal を差し替えて in-memory DB を使う。"""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    monkeypatch.setattr(_models, "engine", engine)
    monkeypatch.setattr(_models, "SessionLocal", Session)
    return Session


def test_reject_action_marks_rejected(isolated_db):
    from chat.repeat_engine import handle_telegram_action

    db = isolated_db()
    offer = OutboundOffer(
        buyer_username="alice",
        trigger="post_feedback_d7",
        past_order_item_id="111",
        draft_subject="Hi",
        draft_body="Thanks!",
        status="awaiting_approval",
        compliance_flags_json="[]",
        due_at=datetime.utcnow() - timedelta(minutes=5),
    )
    db.add(offer)
    db.commit()
    offer_id = offer.id
    db.close()

    cb = {"from": {"username": "tester"}, "message": {}}
    result = handle_telegram_action("reject", offer_id, cb)
    assert result.get("rejected") is True

    db = isolated_db()
    fresh = db.query(OutboundOffer).filter(OutboundOffer.id == offer_id).first()
    assert fresh.status == "rejected"
    assert fresh.approved_by == "tester"
    db.close()


def test_approve_with_block_flag_aborts(isolated_db, monkeypatch):
    """block:* フラグ付きの offer は approve しても sent にならない。"""
    from chat.repeat_engine import handle_telegram_action

    monkeypatch.setattr("chat.repeat_engine.REPEAT_ENGINE_DRY_RUN", True)

    db = isolated_db()
    offer = OutboundOffer(
        buyer_username="alice",
        trigger="post_feedback_d7",
        past_order_item_id="111",
        draft_subject="Hi",
        draft_body="Email me at a@b.com",
        status="awaiting_approval",
        compliance_flags_json='["block:email_address"]',
        due_at=datetime.utcnow() - timedelta(minutes=5),
    )
    db.add(offer)
    db.commit()
    offer_id = offer.id
    db.close()

    cb = {"from": {"username": "tester"}, "message": {}}
    result = handle_telegram_action("approve", offer_id, cb)
    assert result.get("error") == "blocked_by_compliance"

    db = isolated_db()
    fresh = db.query(OutboundOffer).filter(OutboundOffer.id == offer_id).first()
    assert fresh.status == "awaiting_approval"  # 状態は維持
    db.close()


def test_approve_dry_run_marks_sent(isolated_db, monkeypatch):
    from chat.repeat_engine import handle_telegram_action

    monkeypatch.setattr("chat.repeat_engine.REPEAT_ENGINE_DRY_RUN", True)
    monkeypatch.setattr("chat.repeat_engine.REPEAT_ENGINE_DAILY_SEND_CAP", 99)

    db = isolated_db()
    offer = OutboundOffer(
        buyer_username="alice",
        trigger="post_feedback_d7",
        past_order_item_id="111",
        draft_subject="Hi",
        draft_body="Clean message body.",
        status="awaiting_approval",
        compliance_flags_json="[]",
        due_at=datetime.utcnow() - timedelta(minutes=5),
    )
    db.add(offer)
    db.commit()
    offer_id = offer.id
    db.close()

    cb = {"from": {"username": "tester"}, "message": {}}
    result = handle_telegram_action("approve", offer_id, cb)
    assert result.get("sent") is True
    assert result.get("dry_run") is True

    db = isolated_db()
    fresh = db.query(OutboundOffer).filter(OutboundOffer.id == offer_id).first()
    assert fresh.status == "sent"
    assert fresh.sent_at is not None
    db.close()
