"""_build_messages の構造が Anthropic API 仕様を満たすかの構造テスト。

Claude を実呼び出ししない（外部依存を避ける）。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat.repeat_drafts import _build_messages, _FEW_SHOTS_BY_TAG  # noqa: E402


def test_tool_use_followed_by_tool_result():
    """assistant の tool_use 直後に同じ id の tool_result があること。"""
    msgs = _build_messages(
        buyer_username="alice",
        past_title="Some item",
        past_category_tag="figure_collectible",
        delivered_at=None,
        feedback_comment="",
    )

    # 直前が assistant(tool_use) のとき、次は user で content が list、先頭は tool_result
    for i, m in enumerate(msgs[:-1]):
        if m["role"] != "assistant":
            continue
        content = m["content"]
        if not isinstance(content, list):
            continue
        tool_use_ids = [
            b.get("id")
            for b in content
            if isinstance(b, dict) and b.get("type") == "tool_use"
        ]
        if not tool_use_ids:
            continue

        nxt = msgs[i + 1]
        assert nxt["role"] == "user", "tool_use の次は user role 必須"
        assert isinstance(nxt["content"], list), (
            "tool_use の次の user content は list 必須"
        )
        result_ids = [
            b.get("tool_use_id")
            for b in nxt["content"]
            if isinstance(b, dict) and b.get("type") == "tool_result"
        ]
        for tid in tool_use_ids:
            assert tid in result_ids, f"tool_use_id={tid} の tool_result が無い"


def test_message_ends_with_user_request():
    msgs = _build_messages(
        buyer_username="alice",
        past_title="Some item",
        past_category_tag="watch_premium",
        delivered_at=None,
        feedback_comment="",
    )
    last = msgs[-1]
    assert last["role"] == "user"
    text = ""
    if isinstance(last["content"], str):
        text = last["content"]
    else:
        for b in last["content"]:
            if isinstance(b, dict) and b.get("type") == "text":
                text = b.get("text", "")
    assert "Write the draft." in text


def test_unknown_tag_falls_back_to_figure_few_shot():
    msgs = _build_messages(
        buyer_username="alice",
        past_title="",
        past_category_tag="totally_unknown_tag",
        delivered_at=None,
        feedback_comment="",
    )
    # fallback shots と同じ length 構造
    assert len(msgs) == len(_FEW_SHOTS_BY_TAG["figure_collectible"]) + 1


def test_known_tags_have_tool_use_id():
    """各 few-shot の assistant 部分に tool_use ブロックと id があること。"""
    for tag, shots in _FEW_SHOTS_BY_TAG.items():
        assistant_block = shots[-1]
        assert assistant_block["role"] == "assistant", tag
        content = assistant_block["content"]
        assert isinstance(content, list), tag
        tu = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
        assert tu, f"{tag} に tool_use ブロックが無い"
        assert tu[0].get("id"), f"{tag} の tool_use に id が無い"
