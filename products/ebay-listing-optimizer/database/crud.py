"""データベースCRUD操作"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import Base, ChangeHistory, CompetitorCache, Listing, Optimization, SEOScore

_raw_url = os.environ.get("DATABASE_URL", "sqlite:///./optimizer.db")
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


# ============================================================
# Listing CRUD
# ============================================================

async def upsert_listing(session: AsyncSession, **kwargs) -> Listing:
    """出品を追加または更新する"""
    sku = kwargs["sku"]
    result = await session.execute(select(Listing).where(Listing.sku == sku))
    listing = result.scalar_one_or_none()
    if listing is None:
        listing = Listing(**kwargs)
        session.add(listing)
    else:
        for key, value in kwargs.items():
            setattr(listing, key, value)
    await session.commit()
    await session.refresh(listing)
    return listing


async def get_all_listings(session: AsyncSession) -> list[Listing]:
    result = await session.execute(
        select(Listing).order_by(Listing.fetched_at.desc())
    )
    return list(result.scalars().all())


async def get_listing_by_sku(session: AsyncSession, sku: str) -> Optional[Listing]:
    result = await session.execute(select(Listing).where(Listing.sku == sku))
    return result.scalar_one_or_none()


async def get_listing_count(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(Listing.sku)))
    return result.scalar_one()


# ============================================================
# SEO Score CRUD
# ============================================================

async def save_seo_score(session: AsyncSession, **kwargs) -> SEOScore:
    score = SEOScore(**kwargs)
    session.add(score)
    await session.commit()
    await session.refresh(score)
    return score


async def get_latest_score(session: AsyncSession, sku: str) -> Optional[SEOScore]:
    result = await session.execute(
        select(SEOScore)
        .where(SEOScore.sku == sku)
        .order_by(SEOScore.scored_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_all_latest_scores(session: AsyncSession) -> dict[str, SEOScore]:
    """全出品の最新スコアをSKUをキーとした辞書で返す"""
    listings = await get_all_listings(session)
    scores = {}
    for listing in listings:
        score = await get_latest_score(session, listing.sku)
        if score:
            scores[listing.sku] = score
    return scores


# ============================================================
# Optimization CRUD
# ============================================================

async def save_optimization(session: AsyncSession, **kwargs) -> Optimization:
    opt = Optimization(**kwargs)
    session.add(opt)
    await session.commit()
    await session.refresh(opt)
    return opt


async def get_latest_optimization(
    session: AsyncSession, sku: str
) -> Optional[Optimization]:
    result = await session.execute(
        select(Optimization)
        .where(Optimization.sku == sku)
        .order_by(Optimization.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def update_optimization_status(
    session: AsyncSession, opt_id: int, status: str
) -> Optional[Optimization]:
    result = await session.execute(
        select(Optimization).where(Optimization.id == opt_id)
    )
    opt = result.scalar_one_or_none()
    if opt is None:
        return None
    opt.status = status
    if status == "applied":
        opt.applied_at = datetime.utcnow()
    await session.commit()
    await session.refresh(opt)
    return opt


# ============================================================
# Competitor Cache CRUD
# ============================================================

async def get_cached_competitor(
    session: AsyncSession, query: str, category_id: str, ttl_hours: int
) -> Optional[CompetitorCache]:
    """TTL内のキャッシュがあれば返す"""
    result = await session.execute(
        select(CompetitorCache)
        .where(
            CompetitorCache.query == query,
            CompetitorCache.category_id == category_id,
        )
        .order_by(CompetitorCache.cached_at.desc())
        .limit(1)
    )
    cache = result.scalar_one_or_none()
    if cache is None:
        return None
    age_hours = (datetime.utcnow() - cache.cached_at).total_seconds() / 3600
    if age_hours > ttl_hours:
        return None
    return cache


async def save_competitor_cache(session: AsyncSession, **kwargs) -> CompetitorCache:
    cache = CompetitorCache(**kwargs)
    session.add(cache)
    await session.commit()
    return cache


# ============================================================
# Change History CRUD
# ============================================================

async def record_change(session: AsyncSession, **kwargs) -> ChangeHistory:
    change = ChangeHistory(**kwargs)
    session.add(change)
    await session.commit()
    return change


async def get_change_history(
    session: AsyncSession, sku: Optional[str] = None, limit: int = 50
) -> list[ChangeHistory]:
    query = select(ChangeHistory).order_by(ChangeHistory.applied_at.desc()).limit(limit)
    if sku:
        query = query.where(ChangeHistory.sku == sku)
    result = await session.execute(query)
    return list(result.scalars().all())
