from __future__ import annotations

"""④ ポスター — 投稿実行エージェント

タイムスロット分散 + 投稿タイプ別挙動 + 安全装置
"""

import logging
from datetime import datetime

from config import (
    DRY_RUN,
    MAX_POSTS_PER_DAY,
    MIN_POST_INTERVAL_MINUTES,
    THREADS_ACCESS_TOKEN,
    THREADS_USER_ID,
)
from state_manager import (
    add_post_to_history,
    get_post_history,
    is_kill_switch_active,
    pop_from_queue,
)
from threads_api import ThreadsClient

logger = logging.getLogger(__name__)


def _can_post_now(history: list[dict]) -> bool:
    """投稿可能かチェック（間隔 + 日次上限）"""
    today = datetime.now().strftime("%Y-%m-%d")
    today_posts = [p for p in history if p.get("created_at", "").startswith(today)]

    if len(today_posts) >= MAX_POSTS_PER_DAY:
        logger.warning("日次上限 %d件に達しました", MAX_POSTS_PER_DAY)
        return False

    if today_posts:
        last_time_str = today_posts[-1].get("created_at", "")
        if last_time_str:
            try:
                last_time = datetime.fromisoformat(last_time_str)
                elapsed = (datetime.now() - last_time).total_seconds() / 60
                if elapsed < MIN_POST_INTERVAL_MINUTES:
                    logger.info(
                        "最低投稿間隔 %d分未満（%d分経過）",
                        MIN_POST_INTERVAL_MINUTES,
                        int(elapsed),
                    )
                    return False
            except ValueError:
                pass

    return True


async def post_one() -> dict | None:
    """キューから1件取り出して投稿する"""
    if is_kill_switch_active():
        logger.critical("KILL SWITCH有効 — 投稿中止")
        return None

    history = get_post_history()
    if not _can_post_now(history):
        return None

    post = pop_from_queue()
    if not post:
        logger.info("キューが空です")
        return None

    post_type = post.get("post_type", "normal")
    text = post.get("text", "")

    logger.info("投稿開始 [%s]: %s", post_type, text[:60])

    if DRY_RUN:
        logger.info("[DRY RUN] 投稿をスキップ: %s", text[:80])
        post["post_id"] = f"dry_run_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        post["status"] = "dry_run"
        add_post_to_history(post)
        return post

    client = ThreadsClient(access_token=THREADS_ACCESS_TOKEN, user_id=THREADS_USER_ID)

    try:
        if post_type == "comment_bait":
            # コメント誘導型: 本文投稿 → コメント欄に続き
            comment_text = post.get("comment_text", "")
            if comment_text:
                result = await client.post_with_comment(text, comment_text)
                post["post_id"] = result["post_id"]
                post["comment_id"] = result["comment_id"]
            else:
                post["post_id"] = await client.create_text_post(text)

        elif post_type == "thread_tree":
            # ツリー型: 本文 → 返信で連投
            thread_texts = post.get("thread_texts", [])
            all_texts = [text] + thread_texts
            ids = await client.post_thread_tree(all_texts)
            post["post_id"] = ids[0] if ids else ""
            post["thread_ids"] = ids

        elif post_type == "affiliate":
            # アフィリエイト型: 有益投稿 + コメント欄にPRリンク
            pr_comment = post.get("pr_comment", "")
            # writerが選んだリンクがあればそちらを使う
            chosen_link = post.get("affiliate_link", "")
            if chosen_link and pr_comment:
                pr_comment = pr_comment.replace(
                    "https://career.trustmedialab.com/go",
                    chosen_link,
                ).replace(
                    "https://career.trustmedialab.com/go2",
                    chosen_link,
                )
                if chosen_link not in pr_comment:
                    pr_comment = f"{pr_comment}\n{chosen_link}"
            if pr_comment:
                result = await client.post_affiliate(text, pr_comment)
                post["post_id"] = result["post_id"]
                post["comment_id"] = result["comment_id"]
            else:
                post["post_id"] = await client.create_text_post(text)

        else:
            # 通常投稿
            post["post_id"] = await client.create_text_post(text)

        post["status"] = "posted"
        logger.info("投稿成功: %s", post.get("post_id", ""))

    except Exception as e:
        logger.error("投稿失敗: %s", e)
        post["status"] = "error"
        post["error"] = str(e)

    add_post_to_history(post)
    return post


async def run() -> None:
    """ポスターエージェントのメインエントリ（1回の呼び出しで1件投稿）"""
    logger.info("=== ポスター起動 ===")
    result = await post_one()
    if result:
        logger.info("結果: %s — %s", result.get("status"), result.get("post_id", ""))


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
