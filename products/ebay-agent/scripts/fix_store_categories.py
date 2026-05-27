"""ストアカテゴリー修正実行モジュール。

check_store_categories.py から import して使う。
また CLI として直接実行することもできる:
  python fix_store_categories.py new-section "Vintage Audio" item1,item2 --bot-token TOKEN --chat-id ID
"""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Optional

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ebay_core.client import revise_store_category, create_store_section

logger = logging.getLogger(__name__)


def _send_telegram(bot_token: str, chat_id: str, text: str) -> None:
    requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10,
    )


def fix_all(
    mismatches: list[dict],
    bot_token: str,
    chat_id: str,
) -> None:
    """mismatches の全件を修正する。

    mismatch dict keys: item_id, title, current_id, expected_id, expected_name
    """
    ok, fail = 0, 0
    for m in mismatches:
        result = revise_store_category(m["item_id"], m["expected_id"])
        if result["success"]:
            ok += 1
        else:
            fail += 1
            logger.error(f"修正失敗: {m['item_id']} — {result.get('error')}")
        time.sleep(1)

    lines = [f"✅ 修正完了: {ok}件"]
    if fail:
        lines.append(f"❌ 失敗: {fail}件（ログを確認してください）")
    _send_telegram(bot_token, chat_id, "\n".join(lines))


def fix_one(
    mismatch: dict,
    bot_token: str,
    chat_id: str,
) -> None:
    """mismatch の1件だけを修正する。"""
    result = revise_store_category(mismatch["item_id"], mismatch["expected_id"])
    if result["success"]:
        _send_telegram(
            bot_token,
            chat_id,
            f"✅ 修正完了: {mismatch['title'][:50]}... → {mismatch['expected_name']}",
        )
    else:
        _send_telegram(
            bot_token,
            chat_id,
            f"❌ 修正失敗: {mismatch['title'][:50]}...\n{result.get('error')}",
        )


def create_and_assign(
    section_name: str,
    item_ids: list[str],
    parent_id: Optional[str],
    bot_token: str,
    chat_id: str,
) -> None:
    """新セクションを作成し、対象出品を移動する。"""
    result = create_store_section(section_name, parent_id=parent_id)
    if not result["success"]:
        _send_telegram(
            bot_token, chat_id, f"❌ セクション作成失敗: {result.get('error')}"
        )
        return

    new_id = result["section_id"]
    ok, fail = 0, 0
    for item_id in item_ids:
        r = revise_store_category(item_id, new_id)
        if r["success"]:
            ok += 1
        else:
            fail += 1
        time.sleep(1)

    msg = f"✅ セクション「{section_name}」(ID: {new_id}) 作成 → {ok}件移動完了"
    if fail:
        msg += f"\n❌ 移動失敗: {fail}件"
    _send_telegram(bot_token, chat_id, msg)


# ── CLI エントリーポイント ────────────────────────────────

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="cmd")

    p_new = subparsers.add_parser("new-section")
    p_new.add_argument("section_name")
    p_new.add_argument("item_ids")
    p_new.add_argument("--parent-id", default=None)
    p_new.add_argument("--bot-token", required=True)
    p_new.add_argument("--chat-id", required=True)

    args = parser.parse_args()

    if args.cmd == "new-section":
        ids = [i.strip() for i in args.item_ids.split(",") if i.strip()]
        create_and_assign(
            args.section_name, ids, args.parent_id, args.bot_token, args.chat_id
        )
