"""eBay ストアカテゴリー週次チェックスクリプト。

処理フロー:
  1. store_category_rules.yaml を読み込む
  2. GetStore で現在のセクション一覧を取得（ID 検証用）
  3. GetMyeBaySelling で全アクティブ出品のストアセクション情報を取得
  4. キーワード分類 → 不一致リスト + 未分類リスト
  5. 未分類があれば Claude Haiku で新セクション提案
  6. Telegram にレポート送信 (@ssjs_repeat_bot)
  7. 5分間 getUpdates でポーリング → コマンドがあれば実行
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import (
    ANTHROPIC_API_KEY,
    REPEAT_ENGINE_TELEGRAM_BOT_TOKEN as BOT_TOKEN,
    REPEAT_ENGINE_TELEGRAM_CHAT_ID as CHAT_ID,
)
from ebay_core.client import get_store_sections, get_listings_store_info
from scripts.store_category_classify import load_rules, classify_title
from scripts.fix_store_categories import fix_all, fix_one, create_and_assign

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

RULES_PATH = Path(__file__).parent.parent / "config" / "store_category_rules.yaml"
JST = timezone(timedelta(hours=9))
POLL_TIMEOUT_SEC = 300
POLL_INTERVAL_SEC = 8


# ── Telegram ユーティリティ ──────────────────────────────


def _tg_post(method: str, payload: dict) -> dict:
    resp = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        json=payload,
        timeout=15,
    )
    return resp.json()


def _send(text: str) -> None:
    _tg_post("sendMessage", {"chat_id": CHAT_ID, "text": text})


def _get_updates_offset() -> int:
    """現在の最終 update_id + 1 をオフセットとして返す。"""
    result = _tg_post("getUpdates", {"limit": 1, "offset": -1})
    updates = result.get("result", [])
    if updates:
        return updates[-1]["update_id"] + 1
    return 0


def _poll_command(offset: int) -> Optional[str]:
    """指定オフセット以降の Telegram メッセージをポーリングし、コマンド文字列を返す。

    POLL_TIMEOUT_SEC 秒経過してもコマンドがなければ None を返す。
    """
    deadline = time.time() + POLL_TIMEOUT_SEC
    while time.time() < deadline:
        result = _tg_post(
            "getUpdates",
            {"offset": offset, "timeout": POLL_INTERVAL_SEC, "limit": 10},
        )
        for upd in result.get("result", []):
            offset = upd["update_id"] + 1
            text = upd.get("message", {}).get("text", "").strip()
            lower = text.lower()
            if (
                lower in ("fix", "skip")
                or lower.startswith("fix ")
                or lower.startswith("new ")
            ):
                return text
    return None


# ── Claude Haiku 未分類提案 ──────────────────────────────


def _haiku_suggest(
    unclassified_titles: list[str], section_names: list[str]
) -> list[dict]:
    """未分類タイトルを Claude Haiku に渡し、新セクション提案を取得する。

    Returns list of:
      {"action": "assign", "title": "...", "section_name": "Watches"}
      {"action": "new_section", "suggested_name": "Vintage Audio", "titles": ["...", ...]}
    """
    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY 未設定 — Haiku スキップ")
        return []

    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    sections_str = ", ".join(section_names)
    titles_str = "\n".join(f"- {t}" for t in unclassified_titles)

    prompt = f"""You are an eBay store manager. Assign each listing title to the most appropriate store section, or suggest a new section name if none fits.

Existing sections: {sections_str}

Unclassified listings:
{titles_str}

Respond ONLY with valid JSON in this exact format:
{{
  "results": [
    {{"action": "assign", "title": "exact title", "section_name": "existing section name"}},
    {{"action": "new_section", "suggested_name": "New Section Name", "titles": ["title1", "title2"]}}
  ]
}}"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    text = message.content[0].text.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text).get("results", [])
    except json.JSONDecodeError:
        logger.error(f"Haiku JSON parse error: {text[:200]}")
        return []


# ── メイン処理 ───────────────────────────────────────────


def main() -> None:
    now = datetime.now(JST)
    weekday_ja = ["月", "火", "水", "木", "金", "土", "日"][now.weekday()]
    date_str = f"{now.strftime('%Y-%m-%d')} {weekday_ja}"

    logger.info(f"=== eBay ストアカテゴリーチェック開始: {date_str} ===")

    # 1. ルール読み込み
    if not RULES_PATH.exists():
        _send(f"❌ ルールファイルが見つかりません: {RULES_PATH}")
        return
    sections = load_rules(RULES_PATH)
    section_names = list({s.name for s in sections})
    section_id_map = {s.section_id: s for s in sections}

    # 2. GetStore で現在のセクション一覧を取得（ID 検証）
    live_sections = get_store_sections()
    live_ids = {s.section_id for s in live_sections}

    stale_ids = [
        s.section_id
        for s in sections
        if s.section_id not in live_ids and s.section_id != "FILL_IN_FROM_GETSTORE"
    ]
    if stale_ids:
        _send(
            f"⚠️ YAML のセクションID が eBay に存在しません: {stale_ids}\n先に YAML を更新してください。"
        )
        return

    # 3. 出品情報取得
    listings = get_listings_store_info()
    if not listings:
        _send("ℹ️ アクティブ出品が0件でした。")
        return

    # 4. 分類
    mismatches: list[dict] = []
    unclassified: list[dict] = []
    ok_count = 0

    for listing in listings:
        expected = classify_title(listing.title, sections)
        if expected is None:
            unclassified.append({"item_id": listing.item_id, "title": listing.title})
            continue

        if listing.store_section_id == expected.section_id:
            ok_count += 1
        else:
            current_section = section_id_map.get(listing.store_section_id)
            mismatches.append(
                {
                    "item_id": listing.item_id,
                    "title": listing.title,
                    "current_id": listing.store_section_id,
                    "current_name": current_section.name
                    if current_section
                    else f"ID:{listing.store_section_id}",
                    "expected_id": expected.section_id,
                    "expected_name": expected.name,
                }
            )

    # 5. 未分類 → Haiku に投げる
    haiku_results: list[dict] = []
    if unclassified:
        titles = [u["title"] for u in unclassified]
        haiku_results = _haiku_suggest(titles, section_names)

    # 6. Telegram レポート組み立て
    lines = [f"📋 eBayストアカテゴリーチェック（{date_str}）\n"]

    if mismatches:
        lines.append(f"🔄 再割り当て候補: {len(mismatches)}件")
        for i, m in enumerate(mismatches, 1):
            lines.append(
                f'  {i}. "{m["title"][:45]}..." {m["current_name"]} → {m["expected_name"]}'
            )
    else:
        lines.append("🔄 再割り当て候補: なし")

    new_section_proposals: list[dict] = []
    assign_via_haiku: list[dict] = []
    for r in haiku_results:
        if r.get("action") == "new_section":
            new_section_proposals.append(r)
        elif r.get("action") == "assign":
            assign_via_haiku.append(r)

    if new_section_proposals:
        lines.append(f"\n➕ 新セクション提案: {len(new_section_proposals)}件")
        for p in new_section_proposals:
            lines.append(f"  「{p['suggested_name']}」({len(p['titles'])}件)")
            for t in p["titles"][:3]:
                lines.append(f"    - {t[:45]}")

    if unclassified and not haiku_results:
        lines.append(f"\n❓ 未分類（手動確認）: {len(unclassified)}件")
        for u in unclassified[:5]:
            lines.append(f"  - {u['title'][:50]}")

    lines.append(f"\n✅ 問題なし: {ok_count}件")

    if mismatches or new_section_proposals:
        lines.append("\n返信コマンド:")
        if mismatches:
            lines.append("  fix     — 再割り当て候補を全件修正")
            lines.append("  fix N   — N番目だけ修正")
        if new_section_proposals:
            for i, p in enumerate(new_section_proposals, 1):
                lines.append(f"  new {i}   — 「{p['suggested_name']}」を作成して移動")
        lines.append("  skip    — 今回はスキップ")

    report_text = "\n".join(lines)
    logger.info(report_text)

    # 問題がなければレポートのみ送信して終了
    if not mismatches and not new_section_proposals:
        _send(report_text)
        logger.info("問題なし。終了。")
        return

    # 7. Telegram 送信 → ポーリング
    offset = _get_updates_offset()
    _send(report_text)

    logger.info(f"Telegram ポーリング開始（最大 {POLL_TIMEOUT_SEC}秒）...")
    command = _poll_command(offset)

    if command is None:
        logger.info("タイムアウト — 今回はスキップ。")
        return

    command_lower = command.strip().lower()
    logger.info(f"受信コマンド: {command!r}")

    if command_lower == "fix":
        fix_all(mismatches, BOT_TOKEN, CHAT_ID)

    elif command_lower.startswith("fix "):
        try:
            n = int(command_lower.split()[1]) - 1
            fix_one(mismatches[n], BOT_TOKEN, CHAT_ID)
        except (IndexError, ValueError):
            _send(f"⚠️ 無効なコマンド: {command}")

    elif command_lower.startswith("new "):
        try:
            n = int(command_lower.split()[1]) - 1
            proposal = new_section_proposals[n]
            title_to_id = {u["title"]: u["item_id"] for u in unclassified}
            ids = [title_to_id[t] for t in proposal["titles"] if t in title_to_id]
            create_and_assign(proposal["suggested_name"], ids, None, BOT_TOKEN, CHAT_ID)
        except (IndexError, ValueError):
            _send(f"⚠️ 無効なコマンド: {command}")

    elif command_lower == "skip":
        _send("⏭️ スキップしました。次回実行時に再チェックします。")

    else:
        _send(f"⚠️ 不明なコマンド: {command}")

    logger.info("=== チェック完了 ===")


if __name__ == "__main__":
    main()
