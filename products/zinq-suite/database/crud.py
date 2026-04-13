"""ZINQ Suite — データベースCRUD操作"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Literal, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import Base, DiagnosisHistory, User

_raw_url = os.environ.get("DATABASE_URL", "sqlite:///./zinq_suite.db")


def _convert_db_url(url: str) -> str:
    if url.startswith("sqlite:///") and "aiosqlite" not in url:
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    if url.startswith("postgresql://") and "asyncpg" not in url:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://") and "asyncpg" not in url:
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


DATABASE_URL = _convert_db_url(_raw_url)
engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

BotType = Literal["profile", "message", "date", "relation"]
Plan = Literal["free", "standard", "premium"]


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_or_create_user(session: AsyncSession, line_user_id: str) -> User:
    result = await session.execute(select(User).where(User.line_user_id == line_user_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(line_user_id=line_user_id)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def get_user(session: AsyncSession, line_user_id: str) -> Optional[User]:
    result = await session.execute(select(User).where(User.line_user_id == line_user_id))
    return result.scalar_one_or_none()


async def mark_free_diagnosis_used(session: AsyncSession, line_user_id: str) -> User:
    user = await get_or_create_user(session, line_user_id)
    user.free_diagnosis_used = True
    await session.commit()
    await session.refresh(user)
    return user


async def increment_monthly_count(
    session: AsyncSession,
    line_user_id: str,
    bot_type: BotType,
) -> int:
    """月次利用カウントを+1して新しい値を返す"""
    user = await get_or_create_user(session, line_user_id)
    field = f"monthly_{bot_type}_count"
    current = getattr(user, field)
    setattr(user, field, current + 1)
    await session.commit()
    return current + 1


async def reset_monthly_counts(session: AsyncSession, line_user_id: str) -> User:
    """月次カウントをリセット（毎月1日スケジューラーが呼ぶ）"""
    user = await get_or_create_user(session, line_user_id)
    user.monthly_profile_count = 0
    user.monthly_message_count = 0
    user.monthly_date_count = 0
    user.monthly_relation_count = 0
    user.month_reset_at = datetime.utcnow()
    await session.commit()
    await session.refresh(user)
    return user


async def upgrade_user(
    session: AsyncSession,
    line_user_id: str,
    plan: Plan,
    square_customer_id: Optional[str] = None,
    square_subscription_id: Optional[str] = None,
) -> User:
    user = await get_or_create_user(session, line_user_id)
    user.plan = plan
    user.plan_updated_at = datetime.utcnow()
    if square_customer_id:
        user.square_customer_id = square_customer_id
    if square_subscription_id:
        user.square_subscription_id = square_subscription_id
    await session.commit()
    await session.refresh(user)
    return user


async def downgrade_user(session: AsyncSession, line_user_id: str) -> Optional[User]:
    user = await get_user(session, line_user_id)
    if user:
        user.plan = "free"
        user.plan_updated_at = datetime.utcnow()
        user.square_subscription_id = None
        await session.commit()
        await session.refresh(user)
    return user


async def get_user_by_square_subscription(
    session: AsyncSession, subscription_id: str
) -> Optional[User]:
    result = await session.execute(
        select(User).where(User.square_subscription_id == subscription_id)
    )
    return result.scalar_one_or_none()


async def record_diagnosis(
    session: AsyncSession,
    line_user_id: str,
    bot_type: BotType,
    feedback_summary: str,
    score: Optional[float] = None,
    is_free: bool = False,
) -> DiagnosisHistory:
    history = DiagnosisHistory(
        line_user_id=line_user_id,
        bot_type=bot_type,
        score=score,
        feedback_summary=feedback_summary,
        is_free=is_free,
    )
    session.add(history)
    await session.commit()
    await session.refresh(history)
    return history


async def get_user_diagnosis_history(
    session: AsyncSession, line_user_id: str, limit: int = 30
) -> list[DiagnosisHistory]:
    result = await session.execute(
        select(DiagnosisHistory)
        .where(DiagnosisHistory.line_user_id == line_user_id)
        .order_by(DiagnosisHistory.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
