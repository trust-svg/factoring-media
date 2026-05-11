from __future__ import annotations

import pytest

from learning import cli_runner, curator


@pytest.fixture
def company(tmp_path):
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "a.md").write_text("# skill a\n owner: jack\n", encoding="utf-8")
    (skills / "b.md").write_text("# skill b\n owner: tim\n", encoding="utf-8")
    return tmp_path


def test_run_curation_parses_summary_and_snapshots(company, tmp_path, monkeypatch):
    snap_calls = []
    monkeypatch.setattr(
        curator, "_make_snapshot", lambda company_dir, keep: snap_calls.append("snap")
    )
    monkeypatch.setattr(cli_runner, "git_head", lambda repo: "abc123")
    monkeypatch.setattr(
        cli_runner,
        "git_status_short",
        lambda repo: ["A  skills/merged.md", " D skills/a.md"],
    )
    monkeypatch.setattr(cli_runner, "git_checkout_paths", lambda repo, paths: None)
    monkeypatch.setattr(
        cli_runner,
        "run_claude",
        lambda **kw: cli_runner.CliResult(
            True,
            "棚卸ししました\n<summary>before=2 after=1 merged=[a->b] archived=[] created=[merged] fixed=[]</summary>",
            "",
            0,
            False,
        ),
    )
    res = curator.run_curation(
        company_dir=company,
        model="m",
        skill_hits_path=tmp_path / "skill_hits.jsonl",
        snapshot_keep=8,
    )
    assert res["status"] == "done"
    assert "before=2 after=1" in res["summary"]
    assert res["head_before"] == "abc123"
    assert snap_calls == ["snap"]


def test_run_curation_reverts_out_of_bounds(company, tmp_path, monkeypatch):
    monkeypatch.setattr(curator, "_make_snapshot", lambda company_dir, keep: None)
    monkeypatch.setattr(cli_runner, "git_head", lambda repo: "x")
    # skills/.archive は許可、それ以外（secretary/decisions など）は範囲外
    monkeypatch.setattr(
        cli_runner,
        "git_status_short",
        lambda repo: ["A  skills/.archive/old.md", " M secretary/decisions/foo.md"],
    )
    reverted = []
    monkeypatch.setattr(
        cli_runner, "git_checkout_paths", lambda repo, paths: reverted.extend(paths)
    )
    monkeypatch.setattr(
        cli_runner,
        "run_claude",
        lambda **kw: cli_runner.CliResult(
            True,
            "<summary>before=2 after=2 merged=[] archived=[] created=[] fixed=[]</summary>",
            "",
            0,
            False,
        ),
    )
    curator.run_curation(
        company_dir=company,
        model="m",
        skill_hits_path=tmp_path / "h.jsonl",
        snapshot_keep=8,
    )
    assert "secretary/decisions/foo.md" in reverted
    assert "skills/.archive/old.md" not in reverted


def test_run_curation_timeout(company, tmp_path, monkeypatch):
    monkeypatch.setattr(curator, "_make_snapshot", lambda company_dir, keep: None)
    monkeypatch.setattr(cli_runner, "git_head", lambda repo: "x")
    monkeypatch.setattr(cli_runner, "git_status_short", lambda repo: [])
    monkeypatch.setattr(cli_runner, "git_checkout_paths", lambda repo, paths: None)
    monkeypatch.setattr(
        cli_runner,
        "run_claude",
        lambda **kw: cli_runner.CliResult(False, "", "timeout", -1, True),
    )
    res = curator.run_curation(
        company_dir=company,
        model="m",
        skill_hits_path=tmp_path / "h.jsonl",
        snapshot_keep=8,
    )
    assert res["status"] == "error"
    assert "timeout" in res["note"]
