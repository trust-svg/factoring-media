"""データベースCRUD操作"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import AppSetting, Base, Reading, ThreadsPost, ThreadsReply, User

# sqlite:///./uranai.db → sqlite+aiosqlite:///./uranai.db に自動変換
_raw_url = os.environ.get("DATABASE_URL", "sqlite:///./uranai.db")
DATABASE_URL = (
    _raw_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    if _raw_url.startswith("sqlite:///") and "aiosqlite" not in _raw_url
    else _raw_url
)

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """テーブルを初期化する（起動時に一度呼ぶ）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_or_create_user(session: AsyncSession, line_user_id: str) -> User:
    result = await session.execute(
        select(User).where(User.line_user_id == line_user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(line_user_id=line_user_id)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def get_today_reading_count(session: AsyncSession, line_user_id: str) -> int:
    today_start = datetime.combine(date.today(), datetime.min.time())
    result = await session.execute(
        select(func.count(Reading.id))
        .where(Reading.line_user_id == line_user_id)
        .where(Reading.created_at >= today_start)
    )
    return result.scalar_one()


async def get_total_reading_count(session: AsyncSession, line_user_id: str) -> int:
    """通算の送信済み鑑定回数を返す（初回無料チェック用）"""
    result = await session.execute(
        select(func.count(Reading.id))
        .where(Reading.line_user_id == line_user_id)
        .where(Reading.status == "sent")
    )
    return result.scalar_one()


async def record_reading(
    session: AsyncSession,
    line_user_id: str,
    reading_type: str,
    user_message: str,
    draft_text: str,
    status: str = "pending",
) -> Reading:
    reading = Reading(
        line_user_id=line_user_id,
        reading_type=reading_type,
        user_message=user_message,
        draft_text=draft_text,
        status=status,
    )
    session.add(reading)
    await session.commit()
    await session.refresh(reading)
    return reading


async def get_pending_readings(session: AsyncSession) -> list[Reading]:
    """保留中の鑑定一覧を取得"""
    result = await session.execute(
        select(Reading)
        .where(Reading.status == "pending")
        .order_by(Reading.created_at.asc())
    )
    return list(result.scalars().all())


async def get_reading_by_id(session: AsyncSession, reading_id: int) -> Optional[Reading]:
    result = await session.execute(
        select(Reading).where(Reading.id == reading_id)
    )
    return result.scalar_one_or_none()


async def approve_reading(
    session: AsyncSession,
    reading_id: int,
    final_text: str,
) -> Optional[Reading]:
    """鑑定を承認する（編集後テキストを保存）"""
    reading = await get_reading_by_id(session, reading_id)
    if reading is None or reading.status != "pending":
        return None
    reading.result_text = final_text
    reading.status = "approved"
    reading.approved_at = datetime.utcnow()
    await session.commit()
    await session.refresh(reading)
    return reading


async def mark_reading_sent(session: AsyncSession, reading_id: int) -> Optional[Reading]:
    """鑑定をLINE送信済みにする"""
    reading = await get_reading_by_id(session, reading_id)
    if reading is None:
        return None
    reading.status = "sent"
    reading.sent_at = datetime.utcnow()
    await session.commit()
    await session.refresh(reading)
    return reading


async def upgrade_user_plan(
    session: AsyncSession, line_user_id: str, plan: str
) -> User:
    user = await get_or_create_user(session, line_user_id)
    user.plan = plan
    user.plan_updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(user)
    return user


async def get_standard_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).where(User.plan == "standard"))
    return list(result.scalars().all())


async def get_users_for_nurturing(session: AsyncSession, days: int) -> list[User]:
    target = datetime.utcnow() - timedelta(days=days)
    window_start = target.replace(hour=0, minute=0, second=0, microsecond=0)
    window_end = target.replace(hour=23, minute=59, second=59)
    result = await session.execute(
        select(User).where(
            User.joined_at >= window_start,
            User.joined_at <= window_end,
        )
    )
    return list(result.scalars().all())


async def get_recent_posts(session: AsyncSession, days: int) -> list[ThreadsPost]:
    since = datetime.utcnow() - timedelta(days=days)
    result = await session.execute(
        select(ThreadsPost).where(ThreadsPost.posted_at >= since)
    )
    return list(result.scalars().all())


async def record_threads_post(
    session: AsyncSession,
    theme: str,
    content: str,
    post_slot: str,
    threads_post_id: Optional[str] = None,
) -> ThreadsPost:
    post = ThreadsPost(
        theme=theme,
        content=content,
        post_slot=post_slot,
        threads_post_id=threads_post_id,
    )
    session.add(post)
    await session.commit()
    return post


async def update_post_insights(
    session: AsyncSession,
    threads_post_id: str,
    metrics: dict,
) -> Optional[ThreadsPost]:
    """投稿のエンゲージメント指標を更新する"""
    result = await session.execute(
        select(ThreadsPost).where(ThreadsPost.threads_post_id == threads_post_id)
    )
    post = result.scalar_one_or_none()
    if post is None:
        return None
    post.likes = metrics.get("likes", 0)
    post.replies_count = metrics.get("replies", 0)
    post.reposts = metrics.get("reposts", 0)
    post.quotes = metrics.get("quotes", 0)
    post.views = metrics.get("views", 0)
    await session.commit()
    return post


async def get_top_performing_posts(
    session: AsyncSession, limit: int = 5
) -> list[ThreadsPost]:
    """エンゲージメントが高い投稿をスコア順で取得する"""
    since = datetime.utcnow() - timedelta(days=30)
    result = await session.execute(
        select(ThreadsPost)
        .where(ThreadsPost.posted_at >= since)
        .where(ThreadsPost.views > 0)
        .order_by((ThreadsPost.likes + ThreadsPost.replies_count * 3).desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# ===================== ThreadsReply =====================

async def get_reply_by_comment_id(session: AsyncSession, comment_id: str) -> Optional[ThreadsReply]:
    result = await session.execute(
        select(ThreadsReply).where(ThreadsReply.comment_id == comment_id)
    )
    return result.scalar_one_or_none()


async def record_threads_reply(
    session: AsyncSession,
    post_id: str,
    comment_id: str,
    comment_text: str,
    comment_username: str,
    draft_reply: str,
) -> ThreadsReply:
    reply = ThreadsReply(
        post_id=post_id,
        comment_id=comment_id,
        comment_text=comment_text,
        comment_username=comment_username,
        draft_reply=draft_reply,
    )
    session.add(reply)
    await session.commit()
    await session.refresh(reply)
    return reply


async def get_pending_replies(session: AsyncSession) -> list[ThreadsReply]:
    result = await session.execute(
        select(ThreadsReply)
        .where(ThreadsReply.status == "pending")
        .order_by(ThreadsReply.created_at.asc())
    )
    return list(result.scalars().all())


async def approve_reply(
    session: AsyncSession, reply_id: int, final_text: str
) -> Optional[ThreadsReply]:
    result = await session.execute(
        select(ThreadsReply).where(ThreadsReply.id == reply_id)
    )
    reply = result.scalar_one_or_none()
    if reply is None or reply.status != "pending":
        return None
    reply.final_reply = final_text
    reply.status = "approved"
    await session.commit()
    await session.refresh(reply)
    return reply


async def mark_reply_sent(
    session: AsyncSession, reply_id: int, reply_post_id: str
) -> Optional[ThreadsReply]:
    result = await session.execute(
        select(ThreadsReply).where(ThreadsReply.id == reply_id)
    )
    reply = result.scalar_one_or_none()
    if reply is None:
        return None
    reply.reply_post_id = reply_post_id
    reply.status = "sent"
    reply.sent_at = datetime.utcnow()
    await session.commit()
    await session.refresh(reply)
    return reply


async def skip_reply(session: AsyncSession, reply_id: int) -> Optional[ThreadsReply]:
    result = await session.execute(
        select(ThreadsReply).where(ThreadsReply.id == reply_id)
    )
    reply = result.scalar_one_or_none()
    if reply is None:
        return None
    reply.status = "skipped"
    await session.commit()
    await session.refresh(reply)
    return reply


async def get_recent_thread_post_ids(session: AsyncSession, days: int = 3) -> list[str]:
    """直近N日の投稿IDリストを返す（コメントチェック対象）"""
    since = datetime.utcnow() - timedelta(days=days)
    result = await session.execute(
        select(ThreadsPost.threads_post_id)
        .where(ThreadsPost.posted_at >= since)
        .where(ThreadsPost.threads_post_id.is_not(None))
    )
    return [row[0] for row in result.all()]


# ===================== AppSetting =====================

async def get_setting(session: AsyncSession, key: str) -> Optional[str]:
    result = await session.execute(
        select(AppSetting).where(AppSetting.key == key)
    )
    setting = result.scalar_one_or_none()
    return setting.value if setting else None


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    result = await session.execute(
        select(AppSetting).where(AppSetting.key == key)
    )
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
        setting.updated_at = datetime.utcnow()
    else:
        session.add(AppSetting(key=key, value=value))
    await session.commit()
