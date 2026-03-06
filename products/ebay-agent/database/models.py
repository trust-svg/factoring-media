"""統合データベースモデル

ebay-listing-optimizer の既存モデルを拡張し、
仕入れ候補・価格履歴・売上記録を追加。
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from config import DATABASE_URL


class Base(DeclarativeBase):
    pass


# ── 出品管理 ──────────────────────────────────────────────

class Listing(Base):
    """eBay出品データ"""
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
    seo_score: Mapped[int] = mapped_column(Integer, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── SEO最適化 ─────────────────────────────────────────────

class Optimization(Base):
    """AI最適化提案"""
    __tablename__ = "optimizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(128), index=True)
    original_title: Mapped[str] = mapped_column(String(80), default="")
    suggested_title: Mapped[str] = mapped_column(String(80), default="")
    original_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_specifics_json: Mapped[str] = mapped_column(Text, default="{}")
    reasoning: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# ── 仕入れ候補 ────────────────────────────────────────────

class SourceCandidate(Base):
    """日本マーケットプレイスの仕入れ候補"""
    __tablename__ = "source_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(128), index=True, default="")
    search_keyword: Mapped[str] = mapped_column(String(256), default="")
    platform: Mapped[str] = mapped_column(String(32), default="")
    title: Mapped[str] = mapped_column(String(512), default="")
    price_jpy: Mapped[int] = mapped_column(Integer, default=0)
    condition: Mapped[str] = mapped_column(String(64), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str] = mapped_column(Text, default="")
    is_junk: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="found")
    # status: found -> purchased -> shipped -> received
    found_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── 仕入れ実績 ────────────────────────────────────────────

class Procurement(Base):
    """仕入れ実績 — SourceCandidate → 購入 → 受取 → Listing紐付け"""
    __tablename__ = "procurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(128), index=True, default="")
    source_candidate_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    platform: Mapped[str] = mapped_column(String(32), default="")
    title: Mapped[str] = mapped_column(String(512), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    purchase_price_jpy: Mapped[int] = mapped_column(Integer, default=0)
    shipping_cost_jpy: Mapped[int] = mapped_column(Integer, default=0)
    other_cost_jpy: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_jpy: Mapped[int] = mapped_column(Integer, default=0)
    purchase_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    received_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="purchased")
    # status: purchased -> shipped -> received -> listed
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── 価格履歴 ──────────────────────────────────────────────

class PriceHistory(Base):
    """競合価格トラッキング"""
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(128), index=True)
    our_price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    avg_competitor_price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    lowest_competitor_price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    num_competitors: Mapped[int] = mapped_column(Integer, default=0)
    exchange_rate: Mapped[float] = mapped_column(Float, default=0.0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── 売上記録 ──────────────────────────────────────────────

class SalesRecord(Base):
    """売上・利益追跡"""
    __tablename__ = "sales_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    sale_price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    source_cost_jpy: Mapped[int] = mapped_column(Integer, default=0)
    shipping_cost_jpy: Mapped[int] = mapped_column(Integer, default=0)
    ebay_fees_usd: Mapped[float] = mapped_column(Float, default=0.0)
    exchange_rate: Mapped[float] = mapped_column(Float, default=0.0)
    profit_usd: Mapped[float] = mapped_column(Float, default=0.0)
    sold_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── リサーチ結果 ──────────────────────────────────────────

class ResearchResult(Base):
    """需要分析・商品リサーチ結果"""
    __tablename__ = "research_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query: Mapped[str] = mapped_column(String(256), default="")
    category: Mapped[str] = mapped_column(String(128), default="")
    avg_sold_price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    sell_through_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_source_price_jpy: Mapped[int] = mapped_column(Integer, default=0)
    estimated_margin_usd: Mapped[float] = mapped_column(Float, default=0.0)
    num_sold_last_30d: Mapped[int] = mapped_column(Integer, default=0)
    num_active_listings: Mapped[int] = mapped_column(Integer, default=0)
    recommendation: Mapped[str] = mapped_column(Text, default="")
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    researched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── 変更履歴 ──────────────────────────────────────────────

class ChangeHistory(Base):
    """出品変更ログ"""
    __tablename__ = "change_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(128), index=True)
    field_changed: Mapped[str] = mapped_column(String(32), default="")
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text, default="")
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    success: Mapped[int] = mapped_column(Integer, default=1)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ── Instagram投稿 ────────────────────────────────────────

class InstagramPost(Base):
    """Instagram投稿管理"""
    __tablename__ = "instagram_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(128), index=True, default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    hashtags_json: Mapped[str] = mapped_column(Text, default="[]")
    content_type: Mapped[str] = mapped_column(String(32), default="single")
    # content_type: single / carousel / reel_script / story
    tone: Mapped[str] = mapped_column(String(32), default="showcase")
    image_urls_json: Mapped[str] = mapped_column(Text, default="[]")
    slide_suggestions_json: Mapped[str] = mapped_column(Text, default="[]")
    cta: Mapped[str] = mapped_column(String(256), default="")
    ig_post_id: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="draft")
    # status: draft -> scheduled -> published -> archived
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    reach: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    saves: Mapped[int] = mapped_column(Integer, default=0)
    link_clicks: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ── DB初期化 ──────────────────────────────────────────────

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    """テーブル作成"""
    Base.metadata.create_all(engine)


def get_db() -> Session:
    """DBセッションを取得"""
    return SessionLocal()
