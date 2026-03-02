"""データベースCRUD操作"""

import os
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import Base, Reading, ThreadsPost, User

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
    """通算の鑑定回数を返す（初回無料チェック用）"""
    result = await session.execute(
        select(func.count(Reading.id)).where(Reading.line_user_id == line_user_id)
    )
    return result.scalar_one()


async def record_reading(
    session: AsyncSession,
    line_user_id: str,
    reading_type: str,
    result_text: str,
) -> Reading:
    reading = Reading(
        line_user_id=line_user_id,
        reading_type=reading_type,
        result_text=result_text,
    )
    session.add(reading)
    await session.commit()
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
    threads_post_id: str | None = None,
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
