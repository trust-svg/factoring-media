from __future__ import annotations

import datetime as dt

from learning import reviewer


def test_format_conversation_log():
    turns = [
        {
            "turn_idx": 0,
            "role": "user",
            "content": "メルカリ仕入れの重複チェックは？",
            "ts": "2026-05-10T09:00:00",
            "department": "operations",
            "channel_name": "運営-jack-operations",
        },
        {
            "turn_idx": 1,
            "role": "assistant",
            "content": "出品済みSKUと照合してから…",
            "ts": "2026-05-10T09:00:05",
            "department": "operations",
            "channel_name": "運営-jack-operations",
        },
    ]
    log = reviewer.format_conversation_log(
        "運営-jack-operations", "operations", "2026-05-10", turns
    )
    assert "運営-jack-operations" in log
    assert "operations" in log
    assert "2026-05-10" in log
    assert "[user]" in log and "[assistant]" in log
    assert "メルカリ仕入れ" in log
    assert "出品済みSKU" in log


def test_truncate_keeps_head_and_tail():
    turns = [
        {
            "turn_idx": i,
            "role": "user" if i % 2 == 0 else "assistant",
            "content": f"line-{i}-" + "x" * 200,
            "ts": f"2026-05-10T09:{i:02d}:00",
            "department": "operations",
            "channel_name": "c",
        }
        for i in range(60)
    ]
    log = reviewer.format_conversation_log(
        "c", "operations", "2026-05-10", turns, char_limit=2000
    )
    assert len(log) <= 2500  # 上限 + マーカー分の余裕
    assert "line-0-" in log  # 先頭は残る
    assert "line-59-" in log  # 末尾は残る
    assert "（中略" in log


def test_parse_summary():
    out = "作業しました。\n色々やった。\n<summary>done: skills/x.md に追記</summary>\n"
    s = reviewer.parse_summary(out)
    assert s == ("done", "skills/x.md に追記")

    out2 = "<summary>no_learnings: 在庫確認のみ</summary>"
    assert reviewer.parse_summary(out2) == ("no_learnings", "在庫確認のみ")

    # summary 無し → None
    assert reviewer.parse_summary("何も返ってこなかった") is None


import datetime as dt
from pathlib import Path

import pytest

from learning import store, cli_runner


@pytest.fixture
def setup(tmp_path, monkeypatch):
    db = tmp_path / "c.db"
    store.init_db(db)
    company = tmp_path / "company"
    (company / "skills").mkdir(parents=True)
    (company / "secretary" / "memory" / "facts").mkdir(parents=True)
    # ダミー会話
    for i in range(4):
        store.record_turn(
            db,
            "chan-1",
            "運営-jack-operations",
            "operations",
            "s-1",
            "user" if i % 2 == 0 else "assistant",
            f"msg-{i}",
            "cli",
            "chat",
            True,
            now=dt.datetime(2026, 5, 10, 9, i, 0),
        )
    return db, company


def _fake_cli(stdout: str, ok=True, timed_out=False, returncode=0):
    def _run(**kwargs):
        return cli_runner.CliResult(
            ok=ok,
            stdout=stdout,
            stderr="" if ok else "boom",
            returncode=returncode,
            timed_out=timed_out,
        )

    return _run


def test_run_review_done(setup, monkeypatch):
    db, company = setup
    monkeypatch.setattr(
        cli_runner,
        "run_claude",
        _fake_cli("やった\n<summary>done: skills/x.md に追記</summary>"),
    )
    monkeypatch.setattr(cli_runner, "git_status_short", lambda repo: ["A  skills/x.md"])
    monkeypatch.setattr(cli_runner, "git_head", lambda repo: "deadbeef")
    reverted = []
    monkeypatch.setattr(
        cli_runner, "git_checkout_paths", lambda repo, paths: reverted.extend(paths)
    )

    res = reviewer.run_review(
        db_path=db,
        company_dir=company,
        channel_id="chan-1",
        review_date="2026-05-10",
        channel_name="運営-jack-operations",
        department="operations",
        model="m",
        dryrun=False,
        now=dt.datetime(2026, 5, 11, 23, 0),
    )
    assert res["status"] == "done"
    assert "skills/x.md" in res["note"]
    assert reverted == []  # 範囲内なので revert されない
    row = store.get_session_row(db, "chan-1", "2026-05-10")
    assert row["review_status"] == "done"


def test_run_review_no_learnings(setup, monkeypatch):
    db, company = setup
    monkeypatch.setattr(
        cli_runner, "run_claude", _fake_cli("<summary>no_learnings: 雑談</summary>")
    )
    monkeypatch.setattr(cli_runner, "git_status_short", lambda repo: [])
    monkeypatch.setattr(cli_runner, "git_head", lambda repo: "x")
    monkeypatch.setattr(cli_runner, "git_checkout_paths", lambda repo, paths: None)
    res = reviewer.run_review(
        db_path=db,
        company_dir=company,
        channel_id="chan-1",
        review_date="2026-05-10",
        channel_name="c",
        department="operations",
        model="m",
        dryrun=False,
        now=dt.datetime(2026, 5, 11, 23, 0),
    )
    assert res["status"] == "done"
    assert res["note"].startswith("no_learnings")


def test_run_review_timeout(setup, monkeypatch):
    db, company = setup
    monkeypatch.setattr(
        cli_runner, "run_claude", _fake_cli("", ok=False, timed_out=True, returncode=-1)
    )
    monkeypatch.setattr(cli_runner, "git_status_short", lambda repo: [])
    monkeypatch.setattr(cli_runner, "git_head", lambda repo: "x")
    monkeypatch.setattr(cli_runner, "git_checkout_paths", lambda repo, paths: None)
    res = reviewer.run_review(
        db_path=db,
        company_dir=company,
        channel_id="chan-1",
        review_date="2026-05-10",
        channel_name="c",
        department="operations",
        model="m",
        dryrun=False,
        now=dt.datetime(2026, 5, 11, 23, 0),
    )
    assert res["status"] == "error"
    assert "timeout" in res["note"]
    row = store.get_session_row(db, "chan-1", "2026-05-10")
    assert row["review_status"] == "error"


def test_run_review_no_summary(setup, monkeypatch):
    db, company = setup
    monkeypatch.setattr(
        cli_runner, "run_claude", _fake_cli("何か作業はしたが summary を返し忘れた")
    )
    monkeypatch.setattr(cli_runner, "git_status_short", lambda repo: [])
    monkeypatch.setattr(cli_runner, "git_head", lambda repo: "x")
    monkeypatch.setattr(cli_runner, "git_checkout_paths", lambda repo, paths: None)
    res = reviewer.run_review(
        db_path=db,
        company_dir=company,
        channel_id="chan-1",
        review_date="2026-05-10",
        channel_name="c",
        department="operations",
        model="m",
        dryrun=False,
        now=dt.datetime(2026, 5, 11, 23, 0),
    )
    assert res["status"] == "error"
    assert "no_summary" in res["note"]


def test_run_review_out_of_bounds_reverted(setup, monkeypatch):
    db, company = setup
    monkeypatch.setattr(
        cli_runner, "run_claude", _fake_cli("<summary>done: なんか色々</summary>")
    )
    # .env を触ってしまったケース
    monkeypatch.setattr(
        cli_runner, "git_status_short", lambda repo: [" M .env", "A  skills/x.md"]
    )
    monkeypatch.setattr(cli_runner, "git_head", lambda repo: "x")
    reverted = []
    monkeypatch.setattr(
        cli_runner, "git_checkout_paths", lambda repo, paths: reverted.extend(paths)
    )
    res = reviewer.run_review(
        db_path=db,
        company_dir=company,
        channel_id="chan-1",
        review_date="2026-05-10",
        channel_name="c",
        department="operations",
        model="m",
        dryrun=False,
        now=dt.datetime(2026, 5, 11, 23, 0),
    )
    assert ".env" in reverted
    assert "skills/x.md" not in reverted
    assert res["out_of_bounds"] == [".env"]


def test_run_review_out_of_bounds_untracked_cleaned(setup, monkeypatch):
    """範囲外に *新規* ファイルが作られたら（`??`）`git checkout --` ではなく `git clean` で消す。"""
    db, company = setup
    monkeypatch.setattr(
        cli_runner, "run_claude", _fake_cli("<summary>done: 何か</summary>")
    )
    monkeypatch.setattr(
        cli_runner,
        "git_status_short",
        lambda repo: ["?? secretary/decisions/leaked.md", "A  skills/x.md"],
    )
    monkeypatch.setattr(cli_runner, "git_head", lambda repo: "x")
    checked_out = []
    cleaned = []
    monkeypatch.setattr(
        cli_runner, "git_checkout_paths", lambda repo, paths: checked_out.extend(paths)
    )
    monkeypatch.setattr(
        cli_runner, "git_clean_paths", lambda repo, paths: cleaned.extend(paths)
    )
    res = reviewer.run_review(
        db_path=db,
        company_dir=company,
        channel_id="chan-1",
        review_date="2026-05-10",
        channel_name="c",
        department="operations",
        model="m",
        dryrun=False,
        now=dt.datetime(2026, 5, 11, 23, 0),
    )
    assert cleaned == ["secretary/decisions/leaked.md"]
    assert "secretary/decisions/leaked.md" not in checked_out
    assert res["out_of_bounds"] == ["secretary/decisions/leaked.md"]


def test_run_review_dryrun_restricts_tools(setup, monkeypatch):
    db, company = setup
    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return cli_runner.CliResult(
            True, "<summary>no_learnings: dryrun</summary>", "", 0, False
        )

    monkeypatch.setattr(cli_runner, "run_claude", _capture)
    monkeypatch.setattr(cli_runner, "git_status_short", lambda repo: [])
    monkeypatch.setattr(cli_runner, "git_head", lambda repo: "x")
    monkeypatch.setattr(cli_runner, "git_checkout_paths", lambda repo, paths: None)
    reviewer.run_review(
        db_path=db,
        company_dir=company,
        channel_id="chan-1",
        review_date="2026-05-10",
        channel_name="c",
        department="operations",
        model="m",
        dryrun=True,
        now=dt.datetime(2026, 5, 11, 23, 0),
    )
    assert "Write" not in captured["allowed_tools"]
    assert "Edit" not in captured["allowed_tools"]
    assert "Bash" in captured["disallowed_tools"]
