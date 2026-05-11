from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from learning import store


@pytest.fixture
def db(tmp_path: Path):
    path = tmp_path / "test.db"
    store.init_db(path)
    return path


def _record(db_path, **over):
    base = dict(
        db_path=db_path,
        channel_id="chan-1",
        channel_name="運営-jack-operations",
        department="operations",
        cli_session_id="sess-abc",
        role="user",
        content="メルカリ仕入れの重複チェックどうやる？",
        engine="cli",
        origin="chat",
        reviewable=True,
        now=dt.datetime(2026, 5, 10, 9, 0, 0),
    )
    base.update(over)
    return store.record_turn(**base)


def test_record_and_get_session_turns(db):
    _record(db, role="user", content="質問1", now=dt.datetime(2026, 5, 10, 9, 0, 0))
    _record(
        db, role="assistant", content="回答1", now=dt.datetime(2026, 5, 10, 9, 0, 5)
    )
    _record(db, role="user", content="質問2", now=dt.datetime(2026, 5, 10, 9, 1, 0))

    turns = store.get_session_turns(db, "chan-1", "2026-05-10")
    assert [t["role"] for t in turns] == ["user", "assistant", "user"]
    assert [t["content"] for t in turns] == ["質問1", "回答1", "質問2"]
    # turn_idx は (channel_id, review_date) 内の連番
    assert [t["turn_idx"] for t in turns] == [0, 1, 2]


def test_turn_idx_is_per_channel_date_not_per_session(db):
    _record(db, cli_session_id="sess-A", now=dt.datetime(2026, 5, 10, 9, 0, 0))
    _record(db, cli_session_id="sess-B", now=dt.datetime(2026, 5, 10, 20, 0, 0))
    turns = store.get_session_turns(db, "chan-1", "2026-05-10")
    assert [t["turn_idx"] for t in turns] == [0, 1]


def test_sessions_row_upserted(db):
    _record(db, now=dt.datetime(2026, 5, 10, 9, 0, 0))
    _record(db, now=dt.datetime(2026, 5, 10, 9, 5, 0))
    rows = store.get_session_row(db, "chan-1", "2026-05-10")
    assert rows["turn_count"] == 2
    assert rows["first_turn_at"].startswith("2026-05-10T09:00")
    assert rows["last_turn_at"].startswith("2026-05-10T09:05")
    assert rows["origin"] == "chat"
    assert rows["reviewable"] == 1
    assert rows["review_status"] is None


def test_list_pending_reviews(db):
    # 前日のレビュー可能セッション → 対象になる
    _record(db, channel_id="c-old", now=dt.datetime(2026, 5, 10, 9, 0))
    _record(db, channel_id="c-old", now=dt.datetime(2026, 5, 10, 9, 5))
    # 当日（=today 扱い）のセッション → まだ活動が増えるかもしれないので対象外
    # 古すぎる（max_age_days 超）→ 対象外
    _record(db, channel_id="c-ancient", now=dt.datetime(2026, 4, 1, 9, 0))
    _record(db, channel_id="c-ancient", now=dt.datetime(2026, 4, 1, 9, 5))
    # reviewable=False → 対象外
    _record(
        db,
        channel_id="c-noreview",
        reviewable=False,
        now=dt.datetime(2026, 5, 10, 9, 0),
    )
    _record(
        db,
        channel_id="c-noreview",
        reviewable=False,
        now=dt.datetime(2026, 5, 10, 9, 5),
    )
    # ターン数不足（1ターンだけ）→ 対象外（mark_short_skipped 行き）
    _record(db, channel_id="c-short", now=dt.datetime(2026, 5, 10, 9, 0))

    pending = store.list_pending_reviews(
        db, today=dt.date(2026, 5, 11), min_turns=2, max_age_days=2
    )
    chans = {p["channel_id"] for p in pending}
    assert chans == {"c-old"}


def test_mark_review_lifecycle(db):
    _record(db, channel_id="c-1", now=dt.datetime(2026, 5, 10, 9, 0))
    _record(db, channel_id="c-1", now=dt.datetime(2026, 5, 10, 9, 5))
    store.mark_review_start(
        db, "c-1", "2026-05-10", now=dt.datetime(2026, 5, 11, 23, 0)
    )
    row = store.get_session_row(db, "c-1", "2026-05-10")
    assert row["review_status"] == "running"
    store.mark_reviewed(
        db,
        "c-1",
        "2026-05-10",
        "done",
        "skills/x.md に追記",
        now=dt.datetime(2026, 5, 11, 23, 2),
    )
    row = store.get_session_row(db, "c-1", "2026-05-10")
    assert row["review_status"] == "done"
    assert row["reviewed_at"].startswith("2026-05-11T23:02")
    assert row["review_note"] == "skills/x.md に追記"
    # done になったら list_pending_reviews に出ない
    assert store.list_pending_reviews(db, today=dt.date(2026, 5, 12)) == []


def test_requeue_stuck(db):
    _record(db, channel_id="c-1", now=dt.datetime(2026, 5, 10, 9, 0))
    _record(db, channel_id="c-1", now=dt.datetime(2026, 5, 10, 9, 5))
    store.mark_review_start(
        db, "c-1", "2026-05-10", now=dt.datetime(2026, 5, 11, 22, 0)
    )
    # 31分後にチェック → stuck とみなして running を解除
    store.requeue_stuck(db, stuck_minutes=30, now=dt.datetime(2026, 5, 11, 22, 31))
    row = store.get_session_row(db, "c-1", "2026-05-10")
    assert row["review_status"] is None
    assert row["review_started_at"] is None


def test_mark_short_skipped(db):
    _record(db, channel_id="c-short", now=dt.datetime(2026, 5, 10, 9, 0))
    store.mark_short_skipped(db, today=dt.date(2026, 5, 11), min_turns=2)
    row = store.get_session_row(db, "c-short", "2026-05-10")
    assert row["review_status"] == "skipped"
    assert row["review_note"] == "too_short"
