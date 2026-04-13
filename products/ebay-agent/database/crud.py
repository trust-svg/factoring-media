"""CRUD操作"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from database.models import (
    BuyerMessage,
    ChangeHistory,
    InventoryItem,
    Listing,
    MonthlyExpense,
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
        (proc.purchase_price_jpy or 0)
        + (proc.consumption_tax_jpy or 0)
        + (proc.shipping_cost_jpy or 0)
        + (proc.other_cost_jpy or 0)
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
        (proc.purchase_price_jpy or 0)
        + (proc.consumption_tax_jpy or 0)
        + (proc.shipping_cost_jpy or 0)
        + (proc.other_cost_jpy or 0)
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

def calculate_net_profit(record: SalesRecord) -> SalesRecord:
    """SalesRecordの純利益を自動計算"""
    # キャンセル/返金系 → 売上・手数料ゼロ
    if getattr(record, 'progress', '') in ('キャンセル', '返品・返金', '返品なし返金', '未着返金'):
        record.sale_price_usd = 0
        record.ebay_fees_usd = 0
        record.payoneer_fee_usd = 0

    rate = record.exchange_rate or 1.0

    # JPYコスト合算（None安全）
    record.total_cost_jpy = (
        (record.source_cost_jpy or 0)
        + (record.consumption_tax_jpy or 0)
        + (record.shipping_cost_jpy or 0)
        + (record.intl_shipping_cost_jpy or 0)
        + (getattr(record, 'customs_duty_jpy', 0) or 0)
        + (record.other_cost_jpy or 0)
    )

    # USD換算コスト = JPYコスト/レート + USD手数料
    jpy_cost_in_usd = record.total_cost_jpy / rate if record.total_cost_jpy else 0
    usd_fees = record.ebay_fees_usd + record.payoneer_fee_usd
    record.total_cost_usd = round(jpy_cost_in_usd + usd_fees, 2)

    # 純利益
    record.net_profit_usd = round(record.sale_price_usd - record.total_cost_usd, 2)
    record.net_profit_jpy = round(record.net_profit_usd * rate)
    record.profit_margin_pct = round(
        (record.net_profit_usd / record.sale_price_usd * 100) if record.sale_price_usd else 0, 1
    )

    # 旧互換フィールド
    record.profit_usd = record.net_profit_usd
    return record


def add_sales_record(db: Session, **kwargs) -> SalesRecord:
    record = SalesRecord(**kwargs)
    calculate_net_profit(record)
    db.add(record)
    db.commit()
    return record


def update_sales_record(db: Session, record_id: int, **kwargs) -> Optional[SalesRecord]:
    """売上レコードの手動編集（送料・手数料・Payoneerレート等）"""
    record = db.query(SalesRecord).filter(SalesRecord.id == record_id).first()
    if not record:
        return None
    for k, v in kwargs.items():
        if hasattr(record, k) and v is not None:
            setattr(record, k, v)
    calculate_net_profit(record)
    db.commit()
    return record


def get_sales_record(db: Session, record_id: int) -> Optional[SalesRecord]:
    return db.query(SalesRecord).filter(SalesRecord.id == record_id).first()


def get_all_sales(db: Session, year_month: str = "") -> list[SalesRecord]:
    """全売上レコード（年月フィルタ対応: '2026-03'）"""
    q = db.query(SalesRecord)
    if year_month:
        q = q.filter(func.strftime("%Y-%m", SalesRecord.sold_at) == year_month)
    return q.order_by(desc(SalesRecord.sold_at)).all()


def get_sales_summary(db: Session, days: int = 30) -> dict:
    """売上サマリーを取得"""
    cutoff = datetime.utcnow() - timedelta(days=days)
    records = db.query(SalesRecord).filter(SalesRecord.sold_at >= cutoff).all()

    total_revenue = sum(r.sale_price_usd for r in records)
    total_profit = sum(r.net_profit_usd for r in records)
    total_cost_jpy = sum(r.total_cost_jpy for r in records)

    return {
        "period_days": days,
        "total_sales": len(records),
        "total_revenue_usd": round(total_revenue, 2),
        "total_profit_usd": round(total_profit, 2),
        "total_source_cost_jpy": total_cost_jpy,
        "avg_profit_per_sale_usd": round(total_profit / len(records), 2) if records else 0,
        "avg_margin_pct": round((total_profit / total_revenue * 100), 1) if total_revenue else 0,
    }


def get_profit_summary(db: Session, months: int = 6) -> list[dict]:
    """月別利益サマリー"""
    cutoff = datetime.utcnow() - timedelta(days=months * 31)
    records = db.query(SalesRecord).filter(SalesRecord.sold_at >= cutoff).all()

    monthly: dict[str, dict] = {}
    for r in records:
        ym = r.sold_at.strftime("%Y-%m")
        if ym not in monthly:
            monthly[ym] = {
                "year_month": ym, "sales_count": 0,
                "revenue_usd": 0, "revenue_jpy": 0,
                "ebay_fees_usd": 0, "payoneer_fees_usd": 0,
                "source_cost_jpy": 0, "shipping_jpy": 0,
                "intl_shipping_jpy": 0, "other_cost_jpy": 0,
                "total_cost_jpy": 0, "net_profit_usd": 0, "net_profit_jpy": 0,
                "consumption_tax_jpy": 0,
            }
        m = monthly[ym]
        rate = r.exchange_rate or 1.0
        m["sales_count"] += 1
        m["revenue_usd"] += r.sale_price_usd
        m["revenue_jpy"] += round(r.sale_price_usd * rate)
        m["ebay_fees_usd"] += r.ebay_fees_usd
        m["payoneer_fees_usd"] += r.payoneer_fee_usd
        m["source_cost_jpy"] += r.source_cost_jpy
        m["shipping_jpy"] += r.shipping_cost_jpy
        m["intl_shipping_jpy"] += r.intl_shipping_cost_jpy
        m["other_cost_jpy"] += r.other_cost_jpy
        m["total_cost_jpy"] += r.total_cost_jpy
        m["net_profit_usd"] += r.net_profit_usd
        m["net_profit_jpy"] += r.net_profit_jpy
        m["consumption_tax_jpy"] += r.consumption_tax_jpy

    # 固定費を加味
    for ym, m in monthly.items():
        expenses = db.query(MonthlyExpense).filter(MonthlyExpense.year_month == ym).all()
        fixed_cost_jpy = sum(e.amount_jpy for e in expenses)
        m["fixed_cost_jpy"] = fixed_cost_jpy
        m["net_profit_jpy"] -= fixed_cost_jpy
        # 丸め処理
        for k in m:
            if isinstance(m[k], float):
                m[k] = round(m[k], 2)

    return sorted(monthly.values(), key=lambda x: x["year_month"], reverse=True)


def get_profit_breakdown(db: Session, year_month: str) -> dict:
    """特定月の費用内訳"""
    records = get_all_sales(db, year_month=year_month)
    expenses = db.query(MonthlyExpense).filter(MonthlyExpense.year_month == year_month).all()

    source_cost = sum(r.source_cost_jpy for r in records)
    domestic_ship = sum(r.shipping_cost_jpy for r in records)
    intl_ship = sum(r.intl_shipping_cost_jpy for r in records)
    ebay_fees = sum(r.ebay_fees_usd for r in records)
    payoneer_fees = sum(r.payoneer_fee_usd for r in records)
    other = sum(r.other_cost_jpy for r in records)
    fixed = sum(e.amount_jpy for e in expenses)
    revenue = sum(r.sale_price_usd for r in records)
    avg_rate = (sum(r.exchange_rate for r in records) / len(records)) if records else 0

    return {
        "year_month": year_month,
        "sales_count": len(records),
        "revenue_usd": round(revenue, 2),
        "avg_exchange_rate": round(avg_rate, 2),
        "costs": {
            "source_cost_jpy": source_cost,
            "domestic_shipping_jpy": domestic_ship,
            "intl_shipping_jpy": intl_ship,
            "ebay_fees_usd": round(ebay_fees, 2),
            "payoneer_fees_usd": round(payoneer_fees, 2),
            "other_cost_jpy": other,
            "fixed_cost_jpy": fixed,
        },
        "expenses": [
            {"id": e.id, "category": e.category, "description": e.description,
             "amount_jpy": e.amount_jpy, "is_recurring": bool(e.is_recurring)}
            for e in expenses
        ],
    }


# ── MonthlyExpense ───────────────────────────────────────

def add_expense(db: Session, **kwargs) -> MonthlyExpense:
    expense = MonthlyExpense(**kwargs)
    db.add(expense)
    db.commit()
    return expense


def get_expenses(db: Session, year_month: str = "") -> list[MonthlyExpense]:
    q = db.query(MonthlyExpense)
    if year_month:
        q = q.filter(MonthlyExpense.year_month == year_month)
    return q.order_by(desc(MonthlyExpense.created_at)).all()


def update_expense(db: Session, expense_id: int, **kwargs) -> Optional[MonthlyExpense]:
    expense = db.query(MonthlyExpense).filter(MonthlyExpense.id == expense_id).first()
    if not expense:
        return None
    for k, v in kwargs.items():
        if hasattr(expense, k) and v is not None:
            setattr(expense, k, v)
    db.commit()
    return expense


def delete_expense(db: Session, expense_id: int) -> bool:
    expense = db.query(MonthlyExpense).filter(MonthlyExpense.id == expense_id).first()
    if not expense:
        return False
    db.delete(expense)
    db.commit()
    return True


def copy_recurring_expenses(db: Session, from_month: str, to_month: str) -> int:
    """前月の繰り返し固定費を今月にコピー"""
    existing = db.query(MonthlyExpense).filter(MonthlyExpense.year_month == to_month).count()
    if existing > 0:
        return 0  # 既にある場合はスキップ
    recurring = db.query(MonthlyExpense).filter(
        MonthlyExpense.year_month == from_month,
        MonthlyExpense.is_recurring == 1,
    ).all()
    for e in recurring:
        db.add(MonthlyExpense(
            year_month=to_month,
            category=e.category,
            description=e.description,
            amount_jpy=e.amount_jpy,
            amount_usd=e.amount_usd,
            is_recurring=1,
        ))
    db.commit()
    return len(recurring)


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


# ── 有在庫管理 ────────────────────────────────────────────

def get_all_inventory_items(db: Session, status: str = "", date_from: str = "", date_to: str = "") -> list[InventoryItem]:
    """有在庫アイテム一覧（期間フィルター対応）"""
    from datetime import datetime as _dt
    q = db.query(InventoryItem)
    if status:
        q = q.filter(InventoryItem.status == status)
    if date_from:
        try:
            d = _dt.strptime(date_from, "%Y-%m-%d")
            q = q.filter(InventoryItem.purchase_date >= d)
        except ValueError:
            pass
    if date_to:
        try:
            d = _dt.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            q = q.filter(InventoryItem.purchase_date <= d)
        except ValueError:
            pass
    return q.order_by(desc(InventoryItem.id)).all()


def _next_stock_number(db: Session) -> str:
    """次の在庫管理番号を生成（S-0001形式）"""
    import re as _re
    latest = db.query(InventoryItem.stock_number).filter(
        InventoryItem.stock_number.like("S-%")
    ).order_by(desc(InventoryItem.stock_number)).first()
    if latest and latest[0]:
        m = _re.search(r"S-(\d+)", latest[0])
        num = int(m.group(1)) + 1 if m else 1
    else:
        num = 1
    return f"S-{num:04d}"


def add_inventory_item(db: Session, **kwargs) -> InventoryItem:
    """有在庫アイテムを登録（stock_numberが空なら自動採番）"""
    if not kwargs.get("stock_number"):
        kwargs["stock_number"] = _next_stock_number(db)
    item = InventoryItem(**kwargs)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_inventory_item(db: Session, item_id: int, **kwargs) -> Optional[InventoryItem]:
    """有在庫アイテムを更新"""
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        return None
    for k, v in kwargs.items():
        if hasattr(item, k):
            setattr(item, k, v)
    item.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return item


def delete_inventory_item(db: Session, item_id: int) -> bool:
    """有在庫アイテムを削除"""
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        return False
    db.delete(item)
    db.commit()
    return True


def get_inventory_stats(db: Session) -> dict:
    """仕入れ台帳の統計"""
    total = db.query(InventoryItem).count()
    ordered = db.query(InventoryItem).filter(InventoryItem.status == "ordered").count()
    received = db.query(InventoryItem).filter(InventoryItem.status == "received").count()
    in_stock = db.query(InventoryItem).filter(InventoryItem.status == "in_stock").count()
    listed = db.query(InventoryItem).filter(InventoryItem.status == "listed").count()
    sold = db.query(InventoryItem).filter(InventoryItem.status == "sold").count()
    shipped = db.query(InventoryItem).filter(InventoryItem.status == "shipped").count()
    returned = db.query(InventoryItem).filter(InventoryItem.status == "returned").count()
    cancelled = db.query(InventoryItem).filter(InventoryItem.status == "cancelled").count()

    stock_value = db.query(func.sum(InventoryItem.purchase_price_jpy + InventoryItem.consumption_tax_jpy)).filter(
        InventoryItem.status.in_(["in_stock", "received", "listed", "ordered"])
    ).scalar() or 0

    # 平均在庫日数（received + in_stock + listed）
    now = datetime.utcnow()
    active_items = db.query(InventoryItem).filter(
        InventoryItem.status.in_(["in_stock", "received", "listed"]),
        InventoryItem.purchase_date.isnot(None),
    ).all()
    if active_items:
        total_days = sum((now - i.purchase_date).days for i in active_items)
        avg_days = round(total_days / len(active_items))
    else:
        avg_days = 0

    return {
        "total": total,
        "ordered": ordered,
        "received": received,
        "in_stock": in_stock,
        "listed": listed,
        "sold": sold,
        "shipped": shipped,
        "returned": returned,
        "cancelled": cancelled,
        "stock_value_jpy": stock_value,
        "avg_days_in_stock": avg_days,
    }


# ── 利益候補レコメンド ────────────────────────────────────

def get_unlisted_candidates(db: Session) -> list[dict]:
    """未出品の有在庫 + 未在庫登録の受取済み仕入れを候補として収集"""
    candidates = []

    # 1) 有在庫で未出品（in_stock）
    inv_items = db.query(InventoryItem).filter(
        InventoryItem.status == "in_stock"
    ).all()
    for i in inv_items:
        candidates.append({
            "source": "inventory",
            "source_id": i.id,
            "title": i.title,
            "cost_jpy": i.purchase_price_jpy + i.consumption_tax_jpy,
            "purchase_date": i.purchase_date.strftime("%Y-%m-%d") if i.purchase_date else "",
            "platform": i.purchase_source,
            "condition": i.condition,
            "sku": i.sku,
        })

    # 2) 受取済み仕入れで有在庫未登録のもの
    inv_titles = {i.title for i in inv_items}
    procs = db.query(Procurement).filter(
        Procurement.status == "received"
    ).all()
    for p in procs:
        if p.title not in inv_titles:
            candidates.append({
                "source": "procurement",
                "source_id": p.id,
                "title": p.title,
                "cost_jpy": p.total_cost_jpy,
                "purchase_date": p.purchase_date.strftime("%Y-%m-%d") if p.purchase_date else "",
                "platform": p.platform,
                "condition": "",
                "sku": p.sku,
            })

    return candidates


def get_past_sales_by_keyword(db: Session, keywords: list[str]) -> list[dict]:
    """キーワードリストに部分一致する過去の売上実績を取得"""
    results = []
    all_sales = db.query(SalesRecord).filter(
        SalesRecord.sale_price_usd > 0
    ).all()
    for kw in keywords:
        kw_lower = kw.lower()
        matching = [s for s in all_sales if kw_lower in (s.title or "").lower()]
        if matching:
            avg_price = sum(s.sale_price_usd for s in matching) / len(matching)
            avg_profit = sum(s.net_profit_jpy for s in matching) / len(matching)
            avg_margin = sum(s.profit_margin_pct for s in matching) / len(matching)
            results.append({
                "keyword": kw,
                "count": len(matching),
                "avg_price_usd": round(avg_price, 2),
                "avg_profit_jpy": round(avg_profit),
                "avg_margin_pct": round(avg_margin, 1),
            })
    return results


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
    inventory_stats = get_inventory_stats(db)

    return {
        "total_listings": total_listings,
        "out_of_stock": out_of_stock,
        "in_stock": total_listings - out_of_stock,
        "source_candidates": total_candidates,
        "pending_optimizations": pending_opts,
        "pending_procurements": pending_procurements,
        "total_procurement_cost_jpy": total_procurement_cost,
        "sales_30d": sales_30d,
        "inventory": inventory_stats,
    }


# ── Overview ダッシュボード用クエリ ───────────────────────

def get_monthly_achievement(db: Session, year: int, month: int) -> dict:
    """当月の売上・利益・利益率を集計し、目標との比較を返す"""
    from calendar import monthrange
    from datetime import datetime, date
    from config import MONTHLY_REVENUE_TARGET_JPY, MONTHLY_MARGIN_TARGET_PCT, MONTHLY_PROFIT_TARGET_JPY

    _, last_day = monthrange(year, month)
    start = datetime(year, month, 1)
    end = datetime(year, month, last_day, 23, 59, 59)

    records = db.query(SalesRecord).filter(
        SalesRecord.sold_at >= start,
        SalesRecord.sold_at <= end,
    ).all()

    today = date.today()
    # elapsed_days: 当月1日 = 1, 2日 = 2...（当月内の場合）
    elapsed_days = today.day if (today.year == year and today.month == month) else last_day

    # 売上JPY: received_jpy > 0 ならそれ、なければ sale_price_usd * exchange_rate
    def _rev(r: SalesRecord) -> int:
        if r.received_jpy > 0:
            return r.received_jpy
        if r.exchange_rate > 0:
            return int(r.sale_price_usd * r.exchange_rate)
        return 0

    revenue_jpy = sum(_rev(r) for r in records)
    profit_jpy  = sum(r.net_profit_jpy for r in records)
    margin_pct  = round(profit_jpy / revenue_jpy * 100, 1) if revenue_jpy > 0 else 0.0

    projected_revenue = int(revenue_jpy / elapsed_days * last_day) if elapsed_days > 0 else 0
    projected_profit  = int(profit_jpy  / elapsed_days * last_day) if elapsed_days > 0 else 0

    # 利益率の前月同日比
    if month == 1:
        pm_year, pm_month = year - 1, 12
    else:
        pm_year, pm_month = year, month - 1

    _, pm_last = monthrange(pm_year, pm_month)
    pm_day = min(elapsed_days, pm_last)
    pm_records = db.query(SalesRecord).filter(
        SalesRecord.sold_at >= datetime(pm_year, pm_month, 1),
        SalesRecord.sold_at <= datetime(pm_year, pm_month, pm_day, 23, 59, 59),
    ).all()
    pm_rev = sum(_rev(r) for r in pm_records)
    pm_profit = sum(r.net_profit_jpy for r in pm_records)
    pm_margin = round(pm_profit / pm_rev * 100, 1) if pm_rev > 0 else 0.0

    return {
        "period": f"{year}-{month:02d}",
        "elapsed_days": elapsed_days,
        "total_days": last_day,
        "revenue": {
            "actual": revenue_jpy,
            "target": MONTHLY_REVENUE_TARGET_JPY,
            "rate": round(revenue_jpy / MONTHLY_REVENUE_TARGET_JPY * 100, 1) if MONTHLY_REVENUE_TARGET_JPY > 0 else 0.0,
            "projected_eom": projected_revenue,
        },
        "profit_margin": {
            "actual": margin_pct,
            "target": MONTHLY_MARGIN_TARGET_PCT,
            "prev_month_same_day": pm_margin,
        },
        "profit": {
            "actual": profit_jpy,
            "target": MONTHLY_PROFIT_TARGET_JPY,
            "rate": round(profit_jpy / MONTHLY_PROFIT_TARGET_JPY * 100, 1) if MONTHLY_PROFIT_TARGET_JPY > 0 else 0.0,
            "projected_eom": projected_profit,
        },
    }


def get_monthly_calendar(db: Session, year: int, month: int) -> dict:
    """月間の日別売上データ（カレンダー表示用）"""
    from calendar import monthrange
    from datetime import datetime

    _, last_day = monthrange(year, month)
    start = datetime(year, month, 1)
    end = datetime(year, month, last_day, 23, 59, 59)

    records = db.query(SalesRecord).filter(
        SalesRecord.sold_at >= start,
        SalesRecord.sold_at <= end,
    ).all()

    def _rev(r: SalesRecord) -> int:
        if r.received_jpy > 0:
            return r.received_jpy
        if r.exchange_rate > 0:
            return int(r.sale_price_usd * r.exchange_rate)
        return 0

    # 日付ごとに集計
    daily: dict[str, dict] = {}
    for r in records:
        d = r.sold_at.strftime("%Y-%m-%d")
        if d not in daily:
            daily[d] = {"revenue": 0, "orders": 0, "profit": 0}
        daily[d]["revenue"] += _rev(r)
        daily[d]["orders"]  += 1
        daily[d]["profit"]  += r.net_profit_jpy

    days = []
    for day in range(1, last_day + 1):
        d = f"{year}-{month:02d}-{day:02d}"
        entry = daily.get(d, {"revenue": 0, "orders": 0, "profit": 0})
        days.append({"date": d, **entry})

    return {"year": year, "month": month, "days": days}


def get_overview_alerts(db: Session) -> dict:
    """要対応件数（在庫切れ・未読メッセージ・価格アラート）"""
    out_of_stock = db.query(Listing).filter(Listing.quantity == 0).count()
    unread_messages = db.query(BuyerMessage).filter(
        BuyerMessage.is_read == 0,
        BuyerMessage.direction == "inbound",
    ).count()

    # 価格アラート: 最新の価格履歴で競合最安値が自社より10%以上安い出品
    from sqlalchemy import text as sa_text
    price_alerts = db.execute(sa_text("""
        SELECT COUNT(*) FROM price_history ph
        INNER JOIN (
            SELECT sku, MAX(recorded_at) AS max_at FROM price_history GROUP BY sku
        ) latest ON ph.sku = latest.sku AND ph.recorded_at = latest.max_at
        INNER JOIN listings l ON ph.sku = l.sku
        WHERE ph.lowest_competitor_price_usd > 0
          AND ph.lowest_competitor_price_usd < l.price_usd * 0.9
    """)).scalar() or 0

    severity = "ok"
    if out_of_stock >= 10 or unread_messages >= 5:
        severity = "critical"
    elif out_of_stock > 0 or unread_messages > 0 or price_alerts > 0:
        severity = "warning"

    return {
        "out_of_stock": out_of_stock,
        "unread_messages": unread_messages,
        "price_alerts": int(price_alerts),
        "severity": severity,
    }


def get_overview_pace(db: Session) -> dict:
    """今日の売上・前月同日比・全KPI比較データ"""
    from calendar import monthrange
    from datetime import datetime, date, timedelta

    today = date.today()
    today_start = datetime(today.year, today.month, today.day, 0, 0, 0)
    today_end   = datetime(today.year, today.month, today.day, 23, 59, 59)

    def _rev(r: SalesRecord) -> int:
        if r.received_jpy > 0:
            return r.received_jpy
        if r.exchange_rate > 0:
            return int(r.sale_price_usd * r.exchange_rate)
        return 0

    # ── 今日 ──
    today_records = db.query(SalesRecord).filter(
        SalesRecord.sold_at >= today_start,
        SalesRecord.sold_at <= today_end,
    ).all()
    today_revenue = sum(_rev(r) for r in today_records)
    today_orders  = len(today_records)

    # ── 当月累計（今日を含む）──
    month_start = datetime(today.year, today.month, 1)
    month_records = db.query(SalesRecord).filter(
        SalesRecord.sold_at >= month_start,
        SalesRecord.sold_at <= today_end,
    ).all()
    month_revenue = sum(_rev(r) for r in month_records)
    month_order_count = len(month_records)

    # 当月利益率（加重平均）
    total_profit = sum(r.net_profit_jpy for r in month_records)
    profit_margin_actual = round(total_profit / month_revenue * 100, 1) if month_revenue > 0 else 0.0

    # ── 日次平均（今日を除く前の日数）──
    elapsed_before = today.day - 1
    prior_revenue  = month_revenue - today_revenue
    daily_avg = int(prior_revenue / elapsed_before) if elapsed_before > 0 else 0

    # ── 前月同日時点 ──
    if today.month == 1:
        pm_year, pm_month = today.year - 1, 12
    else:
        pm_year, pm_month = today.year, today.month - 1

    _, pm_last = monthrange(pm_year, pm_month)
    pm_day = min(today.day, pm_last)
    pm_end = datetime(pm_year, pm_month, pm_day, 23, 59, 59)
    pm_records = db.query(SalesRecord).filter(
        SalesRecord.sold_at >= datetime(pm_year, pm_month, 1),
        SalesRecord.sold_at <= pm_end,
    ).all()
    pm_revenue = sum(_rev(r) for r in pm_records)
    prev_month_order_count = len(pm_records)

    pm_total_rev = pm_revenue
    pm_total_profit = sum(r.net_profit_jpy for r in pm_records)
    profit_margin_prev = round(pm_total_profit / pm_total_rev * 100, 1) if pm_total_rev > 0 else 0.0

    # 前月同日比
    rev_diff     = month_revenue - pm_revenue
    rev_diff_pct = round(rev_diff / pm_revenue * 100, 1) if pm_revenue > 0 else 0.0

    # ── 出品数・在庫切れ ──
    listing_count      = db.query(Listing).count()
    out_of_stock_count = db.query(Listing).filter(Listing.quantity == 0).count()

    return {
        "today_revenue":   today_revenue,
        "today_orders":    today_orders,
        "daily_avg":       daily_avg,
        "month_revenue":   month_revenue,
        "month_order_count": month_order_count,
        "prev_month_order_count": prev_month_order_count,
        "prev_month_same_day_revenue": pm_revenue,
        "profit_margin_actual": profit_margin_actual,
        "profit_margin_prev":   profit_margin_prev,
        "listing_count":       listing_count,
        "out_of_stock_count":  out_of_stock_count,
        "prev_month_comparison": {
            "revenue_diff":     rev_diff,
            "revenue_diff_pct": rev_diff_pct,
        },
    }


def get_out_of_stock_items(db: Session, limit: int = 10) -> list[dict]:
    """在庫切れ出品リスト（最終売価・切れてから何日か付き）"""
    from datetime import date

    today = date.today()
    oos_listings = (
        db.query(Listing)
        .filter(Listing.quantity == 0)
        .order_by(Listing.title)
        .limit(limit)
        .all()
    )

    result = []
    for listing in oos_listings:
        last_sale = (
            db.query(SalesRecord)
            .filter(SalesRecord.sku == listing.sku)
            .order_by(SalesRecord.sold_at.desc())
            .first()
        )
        last_sale_price_jpy = last_sale.received_jpy if last_sale else 0
        last_sold_at = last_sale.sold_at.date() if last_sale else None
        days_out_of_stock = (today - last_sold_at).days if last_sold_at else None

        result.append({
            "sku":                 listing.sku,
            "title":               listing.title,
            "price_usd":           listing.price_usd,
            "last_sale_price_jpy": last_sale_price_jpy,
            "days_out_of_stock":   days_out_of_stock,
        })
    return result


def get_category_profit(db: Session, year: int, month: int) -> list[dict]:
    """カテゴリ別利益内訳（モーダル用）"""
    from datetime import datetime
    from calendar import monthrange

    month_start = datetime(year, month, 1)
    _, last_day = monthrange(year, month)
    month_end = datetime(year, month, last_day, 23, 59, 59)

    records = (
        db.query(SalesRecord)
        .filter(
            SalesRecord.sold_at >= month_start,
            SalesRecord.sold_at <= month_end,
        )
        .all()
    )

    if not records:
        return []

    skus = list({r.sku for r in records})
    listings = db.query(Listing).filter(Listing.sku.in_(skus)).all()
    sku_to_category = {l.sku: (l.category_name or "その他") for l in listings}

    cat_data: dict[str, dict] = {}
    for rec in records:
        cat = sku_to_category.get(rec.sku, "その他")
        if cat not in cat_data:
            cat_data[cat] = {"revenue": 0, "profit": 0}
        rev = rec.received_jpy if rec.received_jpy > 0 else (int(rec.sale_price_usd * rec.exchange_rate) if rec.exchange_rate > 0 else 0)
        cat_data[cat]["revenue"] += rev
        cat_data[cat]["profit"]  += rec.net_profit_jpy

    total_profit = sum(v["profit"] for v in cat_data.values())

    result = []
    for cat, data in sorted(cat_data.items(), key=lambda x: -x[1]["profit"]):
        margin = round(data["profit"] / data["revenue"] * 100, 1) if data["revenue"] > 0 else 0.0
        pct    = round(data["profit"] / total_profit * 100, 1) if total_profit > 0 else 0.0
        result.append({
            "category":     cat,
            "revenue":      data["revenue"],
            "profit":       data["profit"],
            "margin":       margin,
            "pct_of_total": pct,
        })
    return result


def get_recent_sales(db, year: int, month: int, limit: int = 15):
    """直近の売上明細（ダッシュボード売上明細テーブル用）"""
    from database.models import SalesRecord
    from sqlalchemy import extract

    records = (
        db.query(SalesRecord)
        .filter(
            extract('year',  SalesRecord.sold_at) == year,
            extract('month', SalesRecord.sold_at) == month,
        )
        .order_by(SalesRecord.sold_at.desc())
        .limit(limit)
        .all()
    )

    total_count = (
        db.query(SalesRecord)
        .filter(
            extract('year',  SalesRecord.sold_at) == year,
            extract('month', SalesRecord.sold_at) == month,
        )
        .count()
    )

    result = []
    for r in records:
        rate = r.exchange_rate if r.exchange_rate and r.exchange_rate > 0 else 152.0
        sale_price_jpy = round(r.sale_price_usd * rate) if r.sale_price_usd else 0
        status_map = {
            '発送済': '発送済',
            '納品済': '決済済',
            '未注文': '未発送',
            '注文済': '未発送',
            '':       '未発送',
        }
        status = status_map.get(r.progress, r.progress or '未発送')
        result.append({
            "title":          r.title or '—',
            "sale_price_jpy": sale_price_jpy,
            "profit_jpy":     r.net_profit_jpy or 0,
            "profit_margin":  round(r.profit_margin_pct or 0, 1),
            "status":         status,
            "sold_at":        r.sold_at.strftime("%-m/%-d") if r.sold_at else '—',
        })

    return {"records": result, "total_count": total_count}
