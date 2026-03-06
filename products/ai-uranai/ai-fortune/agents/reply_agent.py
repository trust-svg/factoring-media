"""Threadsコメント自動返信エージェント（半自動: AI下書き → 管理画面で承認）"""
from __future__ import annotations

import logging
import os

import anthropic

from database.crud import (
    AsyncSessionLocal,
    get_recent_thread_post_ids,
    get_reply_by_comment_id,
    record_threads_reply,
)
from threads.api import ThreadsClient

logger = logging.getLogger(__name__)

REPLY_SYSTEM_PROMPT = """あなたは占いサロン Sion のThreadsアカウント担当です。
投稿へのコメントに対して、温かく親しみやすい返信を作成してください。

【返信スタイル】
- 丁寧だけどフレンドリーなトーン
- 短くまとめる（100文字以内が理想）
- コメントの内容に寄り添った返信をする
- 「LINE」への誘導は自然な文脈がある時だけ（無理に入れない）

【禁止事項】
- AIであることを示唆する表現
- 具体的な占い結果を返信で伝えること（LINEで鑑定する旨を案内）
- 断言・保証表現
- ネガティブなコメントへの反論（感謝して流す）

【返信例】
コメント: 「当たってる気がする！」
返信: 「ありがとうございます！ 響くものがあったのですね。今日も良い1日になりますように。」

コメント: 「私は何座ですか？」
返信: 「気になりますよね！ プロフのLINEから生年月日を教えていただければ、詳しくお伝えできますよ。」
"""


async def generate_reply_draft(comment_text: str, post_content: str) -> str:
    """コメントに対するAI返信下書きを生成する"""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        system=REPLY_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"以下の投稿にコメントが付きました。返信文だけを出力してください。\n\n"
                    f"【元投稿】\n{post_content}\n\n"
                    f"【コメント】\n{comment_text}"
                ),
            }
        ],
    )
    return response.content[0].text.strip()


async def check_and_draft_replies() -> int:
    """直近投稿のコメントをチェックし、未対応のものにAI下書きを生成する"""
    threads_client = ThreadsClient()
    my_user_id = threads_client.user_id
    new_count = 0

    async with AsyncSessionLocal() as session:
        post_ids = await get_recent_thread_post_ids(session, days=3)

    if not post_ids:
        logger.info("コメントチェック: 直近投稿なし")
        return 0

    for post_id in post_ids:
        try:
            replies = await threads_client.get_replies(post_id)
        except Exception as e:
            logger.warning(f"コメント取得失敗 post_id={post_id}: {e}")
            continue

        for reply in replies:
            comment_id = reply.get("id", "")
            # 自分自身の返信はスキップ
            if not comment_id:
                continue

            async with AsyncSessionLocal() as session:
                existing = await get_reply_by_comment_id(session, comment_id)
            if existing:
                continue

            comment_text = reply.get("text", "")
            username = reply.get("username", "")

            if not comment_text.strip():
                continue

            # 元投稿の内容を取得（DBから）
            from database.crud import get_recent_posts
            async with AsyncSessionLocal() as session:
                posts = await get_recent_posts(session, days=3)
                post_content = ""
                for p in posts:
                    if p.threads_post_id == post_id:
                        post_content = p.content
                        break

            try:
                draft = await generate_reply_draft(comment_text, post_content)
            except Exception as e:
                logger.error(f"返信下書き生成エラー comment_id={comment_id}: {e}")
                continue

            async with AsyncSessionLocal() as session:
                await record_threads_reply(
                    session,
                    post_id=post_id,
                    comment_id=comment_id,
                    comment_text=comment_text,
                    comment_username=username,
                    draft_reply=draft,
                )
            new_count += 1
            logger.info(f"返信下書き作成: @{username} → {draft[:40]}...")

    return new_count
