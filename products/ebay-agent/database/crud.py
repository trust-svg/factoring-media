"""CRUD操作"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from database.models import (
    ChangeHistory,
    Listing,
    Optimization,
    PriceHistory,
    Procurement,
    ResearchResult,
    SalesRecord,
    SourceCandidate,
)

logger = logging.getLogger(__name__)


# ── Listing ───────────────────────────────────────────────

def upsert_listing(db: Session, **kwargs) -> Listing:
    """出品データをupsert"""
    sku = kwargs["sku"]
    listing = db.query(Listing).filter(Listing.sku == sku).first()
    if listing:
        for k, v in kwargs.items():
            if hasattr(listing, k) and v is not None:
                setattr(listing, k, v)
        listing.fetched_at = datetime.utcnow()
    else:
        listing = Listing(**kwargs)
        db.add(listing)
    db.commit()
    return listing


def get_listing(db: Session, sku: str) -> Optional[Listing]:
    return db.query(Listing).filter(Listing.sku == sku).first()


def get_all_listings(db: Session) -> list[Listing]:
    return db.query(Listing).order_by(desc(Listing.fetched_at)).all()


def get_out_of_stock_listings(db: Session) -> list[Listing]:
    return db.query(Listing).filter(Listing.quantity == 0).all()


# ── SourceCandidate ───────────────────────────────────────

def add_source_candidate(db: Session, **kwargs) -> SourceCandidate:
    candidate = SourceCandidate(**kwargs)
    db.add(candidate)
    db.commit()
    return candidate


def get_source_candidates(db: Session, sku: str = "", keyword: str = "") -> list[SourceCandidate]:
    q = db.query(SourceCandidate)
    if sku:
        q = q.filter(SourceCandidate.sku == sku)
    if keyword:
        q = q.filter(SourceCandidate.search_keyword == keyword)
    return q.order_by(SourceCandidate.price_jpy.asc()).all()


def update_candidate_status(db: Session, candidate_id: int, status: str):
    candidate = db.query(SourceCandidate).filter(SourceCandidate.id == candidate_id).first()
    if candidate:
        candidate.status = status
        db.commit()


# ── Procurement ──────────────────────────────────────────

def add_procurement(db: Session, **kwargs) -> Procurement:
    """仕入れ実績を記録"""
    proc = Procurement(**kwargs)
    proc.total_cost_jpy = (
        proc.purchase_price_jpy + proc.shipping_cost_jpy + proc.other_cost_jpy
    )
    db.add(proc)
    db.commit()
    return proc


def get_procurement_by_sku(db: Session, sku: str) -> list[Procurement]:
    """SKUに紐づく仕入れ実績を取得（新しい順）"""
    return (
        db.query(Procurement)
        .filter(Procurement.sku == sku)
        .order_by(desc(Procurement.created_at))
        .all()
    )


def get_latest_procurement_cost(db: Session, sku: str) -> tuple[int, int]:
    """SKUの最新仕入れ原価を返す (source_cost_jpy, shipping_cost_jpy)"""
    proc = (
        db.query(Procurement)
        .filter(Procurement.sku == sku, Procurement.status == "received")
        .order_by(desc(Procurement.created_at))
        .first()
    )
    if proc:
        return proc.purchase_price_jpy, proc.shipping_cost_jpy
    return 0, 0


def get_all_procurements(db: Session, status: str = "") -> list[Procurement]:
    """全仕入れ実績（ステータスフィルタ付き）"""
    q = db.query(Procurement)
    if status:
        q = q.filter(Procurement.status == status)
    return q.order_by(desc(Procurement.created_at)).all()


def update_procurement(db: Session, proc_id: int, **kwargs) -> Optional[Procurement]:
    """仕入れ実績を更新"""
    proc = db.query(Procurement).filter(Procurement.id == proc_id).first()
    if not proc:
        return None
    for k, v in kwargs.items():
        if hasattr(proc, k) and v is not None:
            setattr(proc, k, v)
    proc.total_cost_jpy = (
        proc.purchase_price_jpy + proc.shipping_cost_jpy + proc.other_cost_jpy
    )
    db.commit()
    return proc


# ── PriceHistory ──────────────────────────────────────────

def add_price_history(db: Session, **kwargs) -> PriceHistory:
    record = PriceHistory(**kwargs)
    db.add(record)
    db.commit()
    return record


def get_price_history(db: Session, sku: str, days: int = 30) -> list[PriceHistory]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    return (
        db.query(PriceHistory)
        .filter(PriceHistory.sku == sku, PriceHistory.recorded_at >= cutoff)
        .order_by(PriceHistory.recorded_at.desc())
        .all()
    )


# ── SalesRecord ───────────────────────────────────────────

def add_sales_record(db: Session, **kwargs) -> SalesRecord:
    record = SalesRecord(**kwargs)
    db.add(record)
    db.commit()
    return record


def get_sales_summary(db: Session, days: int = 30) -> dict:
    """売上サマリーを取得"""
    cutoff = datetime.utcnow() - timedelta(days=days)
    records = db.query(SalesRecord).filter(SalesRecord.sold_at >= cutoff).all()

    total_revenue = sum(r.sale_price_usd for r in records)
    total_profit = sum(r.profit_usd for r in records)
    total_cost_jpy = sum(r.source_cost_jpy for r in records)

    return {
        "period_days": days,
        "total_sales": len(records),
        "total_revenue_usd": round(total_revenue, 2),
        "total_profit_usd": round(total_profit, 2),
        "total_source_cost_jpy": total_cost_jpy,
        "avg_profit_per_sale_usd": round(total_profit / len(records), 2) if records else 0,
        "avg_margin_pct": round((total_profit / total_revenue * 100), 1) if total_revenue else 0,
    }


# ── Optimization ──────────────────────────────────────────

def add_optimization(db: Session, **kwargs) -> Optimization:
    opt = Optimization(**kwargs)
    db.add(opt)
    db.commit()
    return opt


def get_pending_optimizations(db: Session) -> list[Optimization]:
    return db.query(Optimization).filter(Optimization.status == "pending").order_by(desc(Optimization.created_at)).all()


# ── ResearchResult ────────────────────────────────────────

def add_research_result(db: Session, **kwargs) -> ResearchResult:
    result = ResearchResult(**kwargs)
    db.add(result)
    db.commit()
    return result


def get_recent_research(db: Session, limit: int = 20) -> list[ResearchResult]:
    return db.query(ResearchResult).order_by(desc(ResearchResult.researched_at)).limit(limit).all()


# ── ChangeHistory ─────────────────────────────────────────

def log_change(db: Session, sku: str, field: str, old_val: str, new_val: str, success: bool = True, error: str = ""):
    entry = ChangeHistory(
        sku=sku,
        field_changed=field,
        old_value=old_val,
        new_value=new_val,
        success=int(success),
        error_message=error if error else None,
    )
    db.add(entry)
    db.commit()


# ── ダッシュボード用集計 ──────────────────────────────────

def get_dashboard_stats(db: Session) -> dict:
    """ダッシュボード用の統計データ"""
    total_listings = db.query(Listing).count()
    out_of_stock = db.query(Listing).filter(Listing.quantity == 0).count()
    total_candidates = db.query(SourceCandidate).filter(SourceCandidate.status == "found").count()
    pending_opts = db.query(Optimization).filter(Optimization.status == "pending").count()
    pending_procurements = db.query(Procurement).filter(
        Procurement.status.in_(["purchased", "shipped"])
    ).count()
    total_procurement_cost = db.query(func.sum(Procurement.total_cost_jpy)).filter(
        Procurement.status == "received"
    ).scalar() or 0
    sales_30d = get_sales_summary(db, days=30)

    return {
        "total_listings": total_listings,
        "out_of_stock": out_of_stock,
        "in_stock": total_listings - out_of_stock,
        "source_candidates": total_candidates,
        "pending_optimizations": pending_opts,
        "pending_procurements": pending_procurements,
        "total_procurement_cost_jpy": total_procurement_cost,
        "sales_30d": sales_30d,
    }
