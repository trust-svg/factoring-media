from __future__ import annotations

"""⑥ スーパーバイザー — 監視・異常検知エージェント

エラー検知、KILL SWITCH、日次サマリー通知
"""

import json
import logging
from datetime import datetime, timedelta

import httpx

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from state_manager import (
    activate_kill_switch,
    get_post_history,
    get_queue,
    is_kill_switch_active,
    load_state,
)

logger = logging.getLogger(__name__)

CONSECUTIVE_ERROR_LIMIT = 3


async def send_telegram(message: str) -> None:
    """Telegram通知を送信"""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("Telegram Bot Token未設定。通知をスキップ")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                url,
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": message,
                    "parse_mode": "Markdown",
                },
            )
    except Exception as e:
        logger.error("Telegram送信失敗: %s", e)


ERROR_WINDOW_MINUTES = 30


def _check_consecutive_errors(history: list[dict]) -> int:
    """直近30分以内の連続エラー数をカウント"""
    cutoff = datetime.now() - timedelta(minutes=ERROR_WINDOW_MINUTES)
    count = 0
    for post in reversed(history):
        created_at = post.get("created_at", "")
        if not created_at:
            break
        try:
            ts = datetime.fromisoformat(created_at)
        except ValueError:
            break
        if ts < cutoff:
            break
        if post.get("status") == "error":
            count += 1
        else:
            break
    return count


def _check_posting_schedule(history: list[dict]) -> bool:
    """今日の投稿が予定通り実行されているかチェック"""
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now()
    today_posts = [p for p in history if p.get("created_at", "").startswith(today)]

    # 10時を過ぎてるのに1件も投稿がない場合は異常
    if now.hour >= 10 and len(today_posts) == 0:
        return False
    # 14時を過ぎてるのに3件未満の場合も異常
    if now.hour >= 14 and len(today_posts) < 3:
        return False
    return True


async def health_check() -> dict:
    """システム全体のヘルスチェック"""
    result = {
        "timestamp": datetime.now().isoformat(),
        "kill_switch": is_kill_switch_active(),
        "issues": [],
    }

    if result["kill_switch"]:
        result["issues"].append("KILL_SWITCH が有効です")
        return result

    history = get_post_history()
    queue = get_queue()

    # 連続エラーチェック
    consecutive_errors = _check_consecutive_errors(history)
    if consecutive_errors >= CONSECUTIVE_ERROR_LIMIT:
        msg = f"連続エラー {consecutive_errors}回検出 — KILL SWITCH発動"
        result["issues"].append(msg)
        activate_kill_switch(msg)
        await send_telegram(f"🚨 *KILL SWITCH 発動*\n{msg}")
        return result

    # 投稿スケジュールチェック
    if not _check_posting_schedule(history):
        msg = "投稿スケジュールの遅延を検出"
        result["issues"].append(msg)
        await send_telegram(f"⚠️ *スケジュール遅延*\n{msg}")

    # キュー残量チェック
    if len(queue) == 0:
        result["issues"].append("投稿キューが空です")

    result["stats"] = {
        "queue_size": len(queue),
        "total_posts": len(history),
        "consecutive_errors": consecutive_errors,
    }

    return result


async def daily_summary() -> str:
    """日次サマリーを生成してTelegram送信"""
    history = get_post_history()
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    today_posts = [p for p in history if p.get("created_at", "").startswith(today)]
    yesterday_posts = [
        p for p in history if p.get("created_at", "").startswith(yesterday)
    ]

    # 昨日のメトリクスを集計
    total_views = 0
    total_likes = 0
    total_replies = 0
    best_post = None
    best_views = 0

    for p in yesterday_posts:
        metrics = p.get("metrics", {})
        views = metrics.get("views", 0)
        total_views += views
        total_likes += metrics.get("likes", 0)
        total_replies += metrics.get("replies", 0)
        if views > best_views:
            best_views = views
            best_post = p

    queue = get_queue()

    summary = f"""📊 *Threads日次レポート* ({today})

▶ 昨日の実績
  投稿数: {len(yesterday_posts)}件
  総閲覧: {total_views:,}
  総いいね: {total_likes:,}
  総リプライ: {total_replies:,}

▶ 本日の状況
  投稿済み: {len(today_posts)}件
  キュー残: {len(queue)}件
  KILL SW: {"🔴 ON" if is_kill_switch_active() else "🟢 OFF"}"""

    if best_post:
        summary += f"""

▶ ベスト投稿
  {best_post.get("text", "")[:80]}...
  views: {best_views:,} / likes: {best_post.get("metrics", {}).get("likes", 0)}"""

    await send_telegram(summary)
    logger.info("日次サマリー送信完了")
    return summary


async def run() -> None:
    """スーパーバイザーのメインエントリ（ヘルスチェック）"""
    logger.info("=== スーパーバイザー ヘルスチェック ===")
    result = await health_check()
    if result["issues"]:
        for issue in result["issues"]:
            logger.warning("Issue: %s", issue)
    else:
        logger.info("ヘルスチェック OK")


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
