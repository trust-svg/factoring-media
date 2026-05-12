from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from knowledge import digest, store as kstore
from learning import store as lstore
from learning.cli_runner import CliResult


@pytest.fixture
def dbs(tmp_path: Path):
    ldb = tmp_path / "conversations.db"
    kdb = tmp_path / "knowledge.db"
    lstore.init_db(ldb)
    kstore.init_db(kdb)
    return ldb, kdb, tmp_path / "view"


def _turn(ldb, channel_id, role, content, when, **over):
    base = dict(
        db_path=ldb,
        channel_id=channel_id,
        channel_name="運営-jack-operations",
        department="operations",
        cli_session_id="s",
        role=role,
        content=content,
        engine="cli",
        origin="chat",
        reviewable=True,
        now=when,
    )
    base.update(over)
    return lstore.record_turn(**base)


_FAKE_OUT = (
    "## 議事録\n- メルカリ仕入れの重複チェック方針を決めた\n\n"
    "```json\n"
    '{"topics": ["メルカリ仕入れ"], "decisions": [{"text": "差分チェックを9時バッチに", "by": "jack"}], '
    '"open_items": ["駿河屋APIレート確認"], "next_actions": [{"text": "cron追加", "owner": "Hiro"}], '
    '"facts": ["駿河屋APIは1分10req"]}\n'
    "```\n"
)


def _ok(out=_FAKE_OUT):
    return CliResult(ok=True, stdout=out, stderr="", returncode=0, timed_out=False)


def test_build_daily_digests_happy_path(dbs, monkeypatch):
    ldb, kdb, view = dbs
    day = dt.datetime(2026, 5, 12, 9, 0, 0)
    for i in range(6):
        _turn(
            ldb,
            "chan-A",
            "user" if i % 2 == 0 else "assistant",
            f"msg{i}",
            day.replace(minute=i),
        )

    calls = []

    def fake_run(prompt, **kw):
        calls.append(prompt)
        return _ok()

    monkeypatch.setattr("knowledge.digest.run_claude", fake_run)

    res = digest.build_daily_digests(
        date="2026-05-12",
        learning_db=ldb,
        knowledge_db=kdb,
        view_dir=view,
        company_dir=view.parent,
        meetings_dir=view.parent / "no-meetings",
        model="claude-x",
        min_turns=4,
        notification_channel_ids=(),
        timeout_sec=30,
        max_sessions=20,
    )
    assert res.processed == 1
    assert res.failed == 0
    assert len(calls) == 1
    rows = kstore.get_digests(kdb, "2026-05-12")
    assert len(rows) == 1
    assert "メルカリ仕入れ" in rows[0]["summary_md"]
    assert json.loads(rows[0]["decisions_json"])[0]["by"] == "jack"
    # Markdown も出ている
    mds = list((view / "digests").glob("2026-05-12-*.md"))
    assert len(mds) == 1


def test_skips_short_sessions(dbs, monkeypatch):
    ldb, kdb, view = dbs
    day = dt.datetime(2026, 5, 12, 9, 0, 0)
    _turn(ldb, "chan-short", "user", "ちょっとだけ", day)
    _turn(ldb, "chan-short", "assistant", "はい", day.replace(minute=1))  # 2 turns < 4
    monkeypatch.setattr("knowledge.digest.run_claude", lambda *a, **k: _ok())
    res = digest.build_daily_digests(
        date="2026-05-12",
        learning_db=ldb,
        knowledge_db=kdb,
        view_dir=view,
        company_dir=view.parent,
        meetings_dir=view.parent / "nope",
        model="m",
        min_turns=4,
        notification_channel_ids=(),
        timeout_sec=30,
        max_sessions=20,
    )
    assert res.processed == 0
    assert kstore.get_digests(kdb, "2026-05-12") == []


def test_skips_notification_channels(dbs, monkeypatch):
    ldb, kdb, view = dbs
    day = dt.datetime(2026, 5, 12, 9, 0, 0)
    for i in range(6):
        _turn(ldb, "notif-1", "user", f"x{i}", day.replace(minute=i))
    monkeypatch.setattr("knowledge.digest.run_claude", lambda *a, **k: _ok())
    res = digest.build_daily_digests(
        date="2026-05-12",
        learning_db=ldb,
        knowledge_db=kdb,
        view_dir=view,
        company_dir=view.parent,
        meetings_dir=view.parent / "nope",
        model="m",
        min_turns=4,
        notification_channel_ids=("notif-1",),
        timeout_sec=30,
        max_sessions=20,
    )
    assert res.processed == 0


def test_skips_command_only_sessions(dbs, monkeypatch):
    ldb, kdb, view = dbs
    day = dt.datetime(2026, 5, 12, 9, 0, 0)
    for i in range(6):
        # ユーザー発言がすべて "!..." の短文 → コマンドのみセッション
        _turn(
            ldb,
            "cmd-1",
            "user" if i % 2 == 0 else "assistant",
            "!status" if i % 2 == 0 else "OK: 稼働中",
            day.replace(minute=i),
        )
    monkeypatch.setattr("knowledge.digest.run_claude", lambda *a, **k: _ok())
    res = digest.build_daily_digests(
        date="2026-05-12",
        learning_db=ldb,
        knowledge_db=kdb,
        view_dir=view,
        company_dir=view.parent,
        meetings_dir=view.parent / "nope",
        model="m",
        min_turns=4,
        notification_channel_ids=(),
        timeout_sec=30,
        max_sessions=20,
    )
    assert res.processed == 0


def test_claude_failure_is_counted_and_skipped(dbs, monkeypatch):
    ldb, kdb, view = dbs
    day = dt.datetime(2026, 5, 12, 9, 0, 0)
    for i in range(6):
        _turn(
            ldb,
            "chan-A",
            "user" if i % 2 == 0 else "assistant",
            f"m{i}",
            day.replace(minute=i),
        )
    for i in range(6):
        _turn(
            ldb,
            "chan-B",
            "user" if i % 2 == 0 else "assistant",
            f"n{i}",
            day.replace(minute=10 + i),
        )

    def fake_run(prompt, **kw):
        # chan-A 用は成功、chan-B 用は失敗（呼び順で判別）
        fake_run.n += 1
        if fake_run.n == 1:
            return _ok()
        return CliResult(
            ok=False, stdout="", stderr="boom", returncode=1, timed_out=False
        )

    fake_run.n = 0
    monkeypatch.setattr("knowledge.digest.run_claude", fake_run)

    res = digest.build_daily_digests(
        date="2026-05-12",
        learning_db=ldb,
        knowledge_db=kdb,
        view_dir=view,
        company_dir=view.parent,
        meetings_dir=view.parent / "nope",
        model="m",
        min_turns=4,
        notification_channel_ids=(),
        timeout_sec=30,
        max_sessions=20,
    )
    assert res.processed == 1
    assert res.failed == 1
    assert len(kstore.get_digests(kdb, "2026-05-12")) == 1


def test_idempotent_rerun(dbs, monkeypatch):
    ldb, kdb, view = dbs
    day = dt.datetime(2026, 5, 12, 9, 0, 0)
    for i in range(6):
        _turn(
            ldb,
            "chan-A",
            "user" if i % 2 == 0 else "assistant",
            f"m{i}",
            day.replace(minute=i),
        )
    monkeypatch.setattr("knowledge.digest.run_claude", lambda *a, **k: _ok())
    kw = dict(
        date="2026-05-12",
        learning_db=ldb,
        knowledge_db=kdb,
        view_dir=view,
        company_dir=view.parent,
        meetings_dir=view.parent / "nope",
        model="m",
        min_turns=4,
        notification_channel_ids=(),
        timeout_sec=30,
        max_sessions=20,
    )
    digest.build_daily_digests(**kw)
    digest.build_daily_digests(**kw)
    assert len(kstore.get_digests(kdb, "2026-05-12")) == 1


def test_index_council_meetings(dbs):
    ldb, kdb, view = dbs
    meetings = view.parent / "meetings"
    meetings.mkdir(parents=True)
    (meetings / "2026-05-12_経営会議.md").write_text(
        "# 経営会議 2026-05-12\n\n## 議題\n- 新プロダクトの優先順位\n\n（以下略）",
        encoding="utf-8",
    )
    (meetings / "2026-05-11_別の会議.md").write_text("古い会議", encoding="utf-8")
    n = digest.index_council_meetings(
        date="2026-05-12", knowledge_db=kdb, meetings_dir=meetings
    )
    assert n == 1
    rows = [
        r
        for r in kstore.get_digests(kdb, "2026-05-12")
        if r["source_kind"] == "council"
    ]
    assert len(rows) == 1
    assert "経営会議" in rows[0]["summary_md"]
    assert "2026-05-12_経営会議.md" in rows[0]["summary_md"]
