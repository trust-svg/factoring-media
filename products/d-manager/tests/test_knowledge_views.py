from __future__ import annotations

from pathlib import Path

from knowledge import views


def test_write_digest_md_creates_file(tmp_path: Path):
    view_dir = tmp_path / "knowledge"
    p = views.write_digest_md(
        view_dir=view_dir,
        channel_name="運営-jack-operations",
        department="operations",
        date="2026-05-12",
        source_kind="chat",
        summary_md="## 議事録\n- メルカリ仕入れの方針決定",
        topics=["メルカリ仕入れ"],
        decisions=[{"text": "差分チェックを追加", "by": "jack"}],
        open_items=["駿河屋API確認"],
        next_actions=[{"text": "cron 追加", "owner": "Hiro"}],
        facts=["駿河屋APIは1分10req"],
    )
    assert p.exists()
    assert p.parent == view_dir / "digests"
    text = p.read_text(encoding="utf-8")
    assert "メルカリ仕入れの方針決定" in text
    assert "差分チェックを追加" in text
    assert "駿河屋API確認" in text
    # ファイル名は YYYY-MM-DD-<dept>-<channel safe>.md
    assert p.name.startswith("2026-05-12-operations-")
    assert p.suffix == ".md"


def test_write_digest_md_handles_none_sections(tmp_path: Path):
    view_dir = tmp_path / "knowledge"
    p = views.write_digest_md(
        view_dir=view_dir,
        channel_name="x/y:z",
        department="research",
        date="2026-05-12",
        source_kind="council",
        summary_md="council 索引: /path/to/meeting.md",
        topics=None,
        decisions=None,
        open_items=None,
        next_actions=None,
        facts=None,
    )
    assert p.exists()
    # チャンネル名の / : は安全文字に置換される（パスにならない）
    assert "/" not in p.name and ":" not in p.name
