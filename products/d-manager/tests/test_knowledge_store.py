from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge import store


@pytest.fixture
def db(tmp_path: Path):
    path = tmp_path / "knowledge.db"
    store.init_db(path)
    return path


def test_upsert_and_get(db):
    store.upsert_digest(
        db,
        channel_id="chan-1",
        channel_name="運営-jack-operations",
        department="operations",
        date="2026-05-12",
        source_kind="chat",
        turn_count=6,
        summary_md="## 議事録\n- メルカリ仕入れの重複チェック方針を決定",
        topics=["メルカリ仕入れ", "重複チェック"],
        decisions=[{"text": "差分チェックを9時バッチに入れる", "by": "jack"}],
        open_items=["駿河屋の在庫APIレート制限の確認"],
        next_actions=[{"text": "cron に追加", "owner": "Hiro"}],
        facts=["駿河屋APIは1分10リクエスト上限"],
    )
    rows = store.get_digests(db, "2026-05-12")
    assert len(rows) == 1
    r = rows[0]
    assert r["channel_id"] == "chan-1"
    assert r["source_kind"] == "chat"
    assert r["turn_count"] == 6
    assert "メルカリ仕入れ" in r["summary_md"]
    assert json.loads(r["topics_json"]) == ["メルカリ仕入れ", "重複チェック"]
    assert json.loads(r["decisions_json"])[0]["by"] == "jack"


def test_upsert_is_idempotent_per_channel_date(db):
    common = dict(
        db_path=db,
        channel_id="chan-1",
        channel_name="c",
        department="d",
        date="2026-05-12",
        source_kind="chat",
        turn_count=4,
        topics=None,
        decisions=None,
        open_items=None,
        next_actions=None,
        facts=None,
    )
    store.upsert_digest(summary_md="旧", **common)
    store.upsert_digest(summary_md="新", **common)
    rows = store.get_digests(db, "2026-05-12")
    assert len(rows) == 1
    assert rows[0]["summary_md"] == "新"


def test_search_finds_by_substring(db):
    store.upsert_digest(
        db,
        channel_id="c1",
        channel_name="c",
        department="d",
        date="2026-05-12",
        source_kind="chat",
        turn_count=5,
        summary_md="ファクセルのnote公開フローを確認した",
        topics=["note公開"],
        decisions=None,
        open_items=None,
        next_actions=None,
        facts=None,
    )
    hits = store.search(db, "note公開")
    assert any(
        "note公開" in h["summary_md"] or "note公開" in (h["topics_json"] or "")
        for h in hits
    )


def test_get_digests_empty_day_returns_empty_list(db):
    assert store.get_digests(db, "2099-01-01") == []
