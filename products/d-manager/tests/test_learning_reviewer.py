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
