"""データベースモデル定義"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Listing(Base):
    __tablename__ = "listings"

    sku: Mapped[str] = mapped_column(String(128), primary_key=True)
    listing_id: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    category_id: Mapped[str] = mapped_column(String(32), default="")
    category_name: Mapped[str] = mapped_column(String(128), default="")
    condition: Mapped[str] = mapped_column(String(64), default="")
    image_urls_json: Mapped[str] = mapped_column(Text, default="[]")
    item_specifics_json: Mapped[str] = mapped_column(Text, default="{}")
    offer_id: Mapped[str] = mapped_column(String(64), default="")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    scores: Mapped[List["SEOScore"]] = relationship(
        back_populates="listing", cascade="all, delete-orphan"
    )
    optimizations: Mapped[List["Optimization"]] = relationship(
        back_populates="listing", cascade="all, delete-orphan"
    )


class SEOScore(Base):
    __tablename__ = "seo_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(128), ForeignKey("listings.sku"), index=True)
    overall_score: Mapped[int] = mapped_column(Integer, default=0)
    title_score: Mapped[int] = mapped_column(Integer, default=0)
    description_score: Mapped[int] = mapped_column(Integer, default=0)
    specifics_score: Mapped[int] = mapped_column(Integer, default=0)
    photo_score: Mapped[int] = mapped_column(Integer, default=0)
    issues_json: Mapped[str] = mapped_column(Text, default="[]")
    suggestions_json: Mapped[str] = mapped_column(Text, default="[]")
    scored_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    listing: Mapped["Listing"] = relationship(back_populates="scores")


class Optimization(Base):
    __tablename__ = "optimizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(128), ForeignKey("listings.sku"), index=True)
    original_title: Mapped[str] = mapped_column(String(80), default="")
    suggested_title: Mapped[str] = mapped_column(String(80), default="")
    original_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_specifics_json: Mapped[str] = mapped_column(Text, default="{}")
    reasoning: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    # status: pending -> approved -> applied / rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    listing: Mapped["Listing"] = relationship(back_populates="optimizations")


class CompetitorCache(Base):
    __tablename__ = "competitor_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query: Mapped[str] = mapped_column(String(256), default="")
    category_id: Mapped[str] = mapped_column(String(32), default="")
    results_json: Mapped[str] = mapped_column(Text, default="[]")
    keyword_analysis_json: Mapped[str] = mapped_column(Text, default="{}")
    cached_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChangeHistory(Base):
    __tablename__ = "change_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(128), index=True)
    field_changed: Mapped[str] = mapped_column(String(32), default="")
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text, default="")
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    success: Mapped[int] = mapped_column(Integer, default=1)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
