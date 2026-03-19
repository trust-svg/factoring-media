"""分析レポート生成モジュール

週次・月次レポートを自動生成し、DBに保存 + LINE通知。
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import (
    AnalyticsReport,
    InventoryItem,
    Listing,
    MonthlyExpense,
    PriceHistory,
    Procurement,
    SalesRecord,
    SourceCandidate,
    get_db,
)
from database import crud
from comms.line_notify import send_line_message

logger = logging.getLogger(__name__)


# ── データ収集ヘルパー ────────────────────────────────────

def _get_sales_data(db: Session, start: datetime, end: datetime) -> list[SalesRecord]:
    return (
        db.query(SalesRecord)
        .filter(SalesRecord.sold_at >= start, SalesRecord.sold_at < end)
        .all()
    )


def _get_prev_sales_data(db: Session, start: datetime, end: datetime) -> list[SalesRecord]:
    """前期間の売上データ（比較用）"""
    duration = end - start
    prev_start = start - duration
    prev_end = start
    return (
        db.query(SalesRecord)
        .filter(SalesRecord.sold_at >= prev_start, SalesRecord.sold_at < prev_end)
        .all()
    )


def _calc_kpi(records: list[SalesRecord]) -> dict:
    if not records:
        return {
            "total_orders": 0, "total_revenue_usd": 0, "total_profit_usd": 0,
            "avg_order_value_usd": 0, "avg_profit_per_order_usd": 0,
            "avg_margin_pct": 0, "total_source_cost_jpy": 0,
            "total_ebay_fees_usd": 0, "total_payoneer_fees_usd": 0,
        }
    revenue = sum(r.sale_price_usd for r in records)
    profit = sum(r.net_profit_usd for r in records)
    cost_jpy = sum(r.total_cost_jpy for r in records)
    ebay_fees = sum(r.ebay_fees_usd for r in records)
    payoneer_fees = sum(r.payoneer_fee_usd for r in records)
    return {
        "total_orders": len(records),
        "total_revenue_usd": round(revenue, 2),
        "total_profit_usd": round(profit, 2),
        "avg_order_value_usd": round(revenue / len(records), 2),
        "avg_profit_per_order_usd": round(profit / len(records), 2),
        "avg_margin_pct": round((profit / revenue * 100), 1) if revenue else 0,
        "total_source_cost_jpy": cost_jpy,
        "total_ebay_fees_usd": round(ebay_fees, 2),
        "total_payoneer_fees_usd": round(payoneer_fees, 2),
    }


def _calc_comparison(current_kpi: dict, prev_kpi: dict) -> dict:
    """前期比較（変化率）"""
    comp = {}
    for key in ["total_orders", "total_revenue_usd", "total_profit_usd", "avg_margin_pct"]:
        curr = current_kpi.get(key, 0)
        prev = prev_kpi.get(key, 0)
        if prev:
            change_pct = round((curr - prev) / abs(prev) * 100, 1)
        else:
            change_pct = 100.0 if curr else 0
        comp[key] = {"current": curr, "previous": prev, "change_pct": change_pct}
    return comp


def _top_products(records: list[SalesRecord], limit: int = 10, worst: bool = False) -> list[dict]:
    sku_map: dict[str, dict] = defaultdict(
        lambda: {"title": "", "revenue": 0, "profit": 0, "count": 0, "margin_pct": 0}
    )
    for r in records:
        sku_map[r.sku]["title"] = r.title
        sku_map[r.sku]["revenue"] += r.sale_price_usd
        sku_map[r.sku]["profit"] += r.net_profit_usd
        sku_map[r.sku]["count"] += 1

    items = []
    for sku, d in sku_map.items():
        margin = round((d["profit"] / d["revenue"] * 100), 1) if d["revenue"] else 0
        items.append({
            "sku": sku,
            "title": d["title"][:60],
            "revenue_usd": round(d["revenue"], 2),
            "profit_usd": round(d["profit"], 2),
            "sales_count": d["count"],
            "margin_pct": margin,
        })

    if worst:
        return sorted(items, key=lambda x: x["profit_usd"])[:limit]
    return sorted(items, key=lambda x: x["revenue_usd"], reverse=True)[:limit]


def _buyer_country_breakdown(records: list[SalesRecord]) -> list[dict]:
    country_map: dict[str, dict] = defaultdict(lambda: {"orders": 0, "revenue": 0})
    for r in records:
        c = r.buyer_country or "Unknown"
        country_map[c]["orders"] += 1
        country_map[c]["revenue"] += r.sale_price_usd
    return sorted(
        [{"country": k, "orders": v["orders"], "revenue_usd": round(v["revenue"], 2)}
         for k, v in country_map.items()],
        key=lambda x: x["revenue_usd"], reverse=True,
    )


def _inventory_analysis(db: Session) -> dict:
    total_listings = db.query(Listing).count()
    out_of_stock = db.query(Listing).filter(Listing.quantity == 0).count()
    in_stock = total_listings - out_of_stock

    # デッドストック（30日以上在庫あり未売）
    cutoff_30d = datetime.utcnow() - timedelta(days=30)
    dead_stock = (
        db.query(InventoryItem)
        .filter(
            InventoryItem.status.in_(["in_stock", "listed", "received"]),
            InventoryItem.created_at < cutoff_30d,
        )
        .all()
    )
    dead_stock_list = [
        {
            "sku": i.sku, "title": i.title[:50],
            "days": (datetime.utcnow() - i.created_at).days,
            "cost_jpy": i.purchase_price_jpy,
        }
        for i in dead_stock[:10]
    ]

    # 平均回転日数（売れたアイテム）
    sold_items = (
        db.query(InventoryItem)
        .filter(
            InventoryItem.status.in_(["sold", "shipped"]),
            InventoryItem.purchase_date.isnot(None),
            InventoryItem.sold_at.isnot(None),
        )
        .all()
    )
    if sold_items:
        avg_turnover = round(
            sum((i.sold_at - i.purchase_date).days for i in sold_items) / len(sold_items), 1
        )
    else:
        avg_turnover = 0

    # 仕入れ待ち
    pending_proc = db.query(Procurement).filter(
        Procurement.status.in_(["purchased", "shipped"])
    ).count()

    return {
        "total_listings": total_listings,
        "in_stock": in_stock,
        "out_of_stock": out_of_stock,
        "out_of_stock_rate_pct": round(out_of_stock / total_listings * 100, 1) if total_listings else 0,
        "dead_stock_count": len(dead_stock),
        "dead_stock_items": dead_stock_list,
        "avg_turnover_days": avg_turnover,
        "pending_procurements": pending_proc,
    }


def _procurement_analysis(db: Session, start: datetime, end: datetime) -> dict:
    procs = (
        db.query(Procurement)
        .filter(Procurement.created_at >= start, Procurement.created_at < end)
        .all()
    )
    platform_map: dict[str, dict] = defaultdict(lambda: {"count": 0, "total_jpy": 0})
    for p in procs:
        platform_map[p.platform or "other"]["count"] += 1
        platform_map[p.platform or "other"]["total_jpy"] += p.total_cost_jpy

    platforms = sorted(
        [{"platform": k, "count": v["count"], "total_cost_jpy": v["total_jpy"]}
         for k, v in platform_map.items()],
        key=lambda x: x["total_cost_jpy"], reverse=True,
    )
    total_cost = sum(p.total_cost_jpy for p in procs)

    return {
        "total_items": len(procs),
        "total_cost_jpy": total_cost,
        "avg_cost_jpy": round(total_cost / len(procs)) if procs else 0,
        "platforms": platforms,
    }


def _category_breakdown(records: list[SalesRecord], db: Session) -> list[dict]:
    """カテゴリ別売上（Listingテーブルのcategory_nameを使用）"""
    sku_cats: dict[str, str] = {}
    skus = list({r.sku for r in records})
    if skus:
        listings = db.query(Listing).filter(Listing.sku.in_(skus)).all()
        for l in listings:
            sku_cats[l.sku] = l.category_name or "Uncategorized"

    cat_map: dict[str, dict] = defaultdict(lambda: {"orders": 0, "revenue": 0, "profit": 0})
    for r in records:
        cat = sku_cats.get(r.sku, "Uncategorized")
        cat_map[cat]["orders"] += 1
        cat_map[cat]["revenue"] += r.sale_price_usd
        cat_map[cat]["profit"] += r.net_profit_usd

    return sorted(
        [{
            "category": k, "orders": v["orders"],
            "revenue_usd": round(v["revenue"], 2),
            "profit_usd": round(v["profit"], 2),
            "margin_pct": round(v["profit"] / v["revenue"] * 100, 1) if v["revenue"] else 0,
        } for k, v in cat_map.items()],
        key=lambda x: x["revenue_usd"], reverse=True,
    )


def _price_competitiveness(db: Session, days: int = 7) -> dict:
    cutoff = datetime.utcnow() - timedelta(days=days)
    records = db.query(PriceHistory).filter(PriceHistory.recorded_at >= cutoff).all()
    if not records:
        return {"checked": 0, "cheaper": 0, "competitive": 0, "expensive": 0}

    cheaper = sum(1 for r in records if r.our_price_usd < r.lowest_competitor_price_usd * 0.95)
    expensive = sum(1 for r in records if r.our_price_usd > r.avg_competitor_price_usd * 1.10)
    competitive = len(records) - cheaper - expensive

    return {
        "checked": len(records),
        "cheaper_than_lowest": cheaper,
        "competitive": competitive,
        "more_expensive": expensive,
    }


def _generate_suggestions(kpi: dict, inventory: dict, procurement: dict, comparison: dict) -> list[dict]:
    """データに基づくAI改善提案"""
    suggestions = []

    # 利益率チェック
    margin = kpi.get("avg_margin_pct", 0)
    if margin < 15:
        suggestions.append({
            "category": "pricing",
            "priority": "high",
            "title": "利益率が低い",
            "detail": f"平均利益率 {margin}% — 目標20%以上。価格見直しまたは仕入れコスト削減を検討。",
            "action": "価格モニターで競合と10%以上差がある商品を特定し、値上げを検討",
        })
    elif margin > 30:
        suggestions.append({
            "category": "scaling",
            "priority": "medium",
            "title": "高利益率 — スケーリングの余地あり",
            "detail": f"平均利益率 {margin}% は非常に良好。出品数拡大で総利益を増やせる可能性。",
            "action": "同カテゴリの新商品リサーチを強化",
        })

    # 在庫切れ
    oos_rate = inventory.get("out_of_stock_rate_pct", 0)
    if oos_rate > 20:
        suggestions.append({
            "category": "inventory",
            "priority": "high",
            "title": "在庫切れ率が高い",
            "detail": f"在庫切れ率 {oos_rate}% — 売上機会を逃している可能性。",
            "action": "在庫切れ商品の仕入れ先を自動検索し、優先的に補充",
        })

    # デッドストック
    dead = inventory.get("dead_stock_count", 0)
    if dead > 5:
        suggestions.append({
            "category": "inventory",
            "priority": "medium",
            "title": f"デッドストック {dead}件",
            "detail": "30日以上売れていない商品あり。値下げまたは取り下げを検討。",
            "action": "デッドストック商品の価格を競合最安値に合わせるか、バンドル販売を検討",
        })

    # 売上トレンド
    rev_change = comparison.get("total_revenue_usd", {}).get("change_pct", 0)
    if rev_change < -10:
        suggestions.append({
            "category": "sales",
            "priority": "high",
            "title": f"売上が前期比 {rev_change}% 減少",
            "detail": "売上が大幅に下落。出品数・価格・季節要因を確認。",
            "action": "トップ商品の在庫確認、新商品の追加出品、プロモーション検討",
        })
    elif rev_change > 20:
        suggestions.append({
            "category": "sales",
            "priority": "low",
            "title": f"売上が前期比 +{rev_change}% 成長",
            "detail": "好調な成長。この勢いを維持するため、在庫確保と新商品投入を継続。",
            "action": "売れ筋カテゴリの出品数を増やす",
        })

    # 仕入れコスト
    avg_cost = procurement.get("avg_cost_jpy", 0)
    if avg_cost > 10000:
        suggestions.append({
            "category": "procurement",
            "priority": "medium",
            "title": "平均仕入れ単価が高い",
            "detail": f"平均 ¥{avg_cost:,} — 低コスト商品も混ぜてリスク分散を。",
            "action": "¥3,000以下の小物カテゴリのリサーチを追加",
        })

    return suggestions


def _generate_tool_suggestions(kpi: dict, inventory: dict) -> list[dict]:
    """ツール開発提案"""
    tools = []

    tools.append({
        "name": "自動値下げスケジューラー",
        "description": "一定期間売れない商品を自動で段階的に値下げするツール",
        "priority": "high",
        "reason": "デッドストック削減と回転率向上",
    })
    tools.append({
        "name": "仕入れ先リピートアラート",
        "description": "過去に良い仕入れ実績のある出品者の新規出品を自動通知",
        "priority": "medium",
        "reason": "信頼できる仕入れ先からの効率的な仕入れ",
    })
    tools.append({
        "name": "為替レート最適化",
        "description": "為替変動に基づいてUSD価格を自動調整する提案ツール",
        "priority": "medium",
        "reason": "円安/円高時の利益確保",
    })
    tools.append({
        "name": "バンドル販売提案",
        "description": "関連商品を組み合わせたセット販売の提案を自動生成",
        "priority": "low",
        "reason": "客単価向上とデッドストック解消",
    })
    tools.append({
        "name": "季節トレンドアラート",
        "description": "過去の売上データから季節需要を予測し、仕入れタイミングを通知",
        "priority": "medium",
        "reason": "需要ピーク前の先行仕入れで利益最大化",
    })

    return tools


# ── レポート生成メイン ────────────────────────────────────

def generate_report(report_type: str, target_date: datetime | None = None) -> dict:
    """
    レポートを生成してDBに保存。

    Args:
        report_type: "weekly" or "monthly"
        target_date: 基準日（Noneなら今日）

    Returns:
        生成されたレポートデータ
    """
    if target_date is None:
        target_date = datetime.utcnow()

    db = get_db()
    try:
        # 期間計算
        if report_type == "weekly":
            # 直近の月曜日から日曜日
            days_since_monday = target_date.weekday()
            end = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            start = end - timedelta(days=days_since_monday + 7)
            end = start + timedelta(days=7)
            week_num = start.isocalendar()[1]
            period_label = f"{start.year}-W{week_num:02d}"
        else:
            # 前月
            first_of_month = target_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end = first_of_month
            start = (first_of_month - timedelta(days=1)).replace(day=1)
            period_label = start.strftime("%Y-%m")

        # 重複チェック
        existing = (
            db.query(AnalyticsReport)
            .filter(
                AnalyticsReport.report_type == report_type,
                AnalyticsReport.period_label == period_label,
            )
            .first()
        )
        if existing:
            logger.info(f"Report {report_type} {period_label} already exists (id={existing.id})")
            return _report_to_dict(existing)

        # データ収集
        records = _get_sales_data(db, start, end)
        prev_records = _get_prev_sales_data(db, start, end)

        kpi = _calc_kpi(records)
        prev_kpi = _calc_kpi(prev_records)
        comparison = _calc_comparison(kpi, prev_kpi)
        top = _top_products(records, limit=10)
        worst = _top_products(records, limit=5, worst=True)
        countries = _buyer_country_breakdown(records)
        inventory = _inventory_analysis(db)
        procurement = _procurement_analysis(db, start, end)
        categories = _category_breakdown(records, db)
        price_comp = _price_competitiveness(db, days=7 if report_type == "weekly" else 30)
        suggestions = _generate_suggestions(kpi, inventory, procurement, comparison)
        tool_suggestions = _generate_tool_suggestions(kpi, inventory)

        # DB保存
        report = AnalyticsReport(
            report_type=report_type,
            period_start=start,
            period_end=end,
            period_label=period_label,
            kpi_json=json.dumps(kpi),
            top_products_json=json.dumps(top),
            worst_products_json=json.dumps(worst),
            inventory_json=json.dumps(inventory),
            procurement_json=json.dumps(procurement),
            category_json=json.dumps(categories),
            buyer_country_json=json.dumps(countries),
            price_competitiveness_json=json.dumps(price_comp),
            comparison_json=json.dumps(comparison),
            suggestions_json=json.dumps(suggestions),
            tool_suggestions_json=json.dumps(tool_suggestions),
        )
        db.add(report)
        db.commit()
        db.refresh(report)

        logger.info(f"Report generated: {report_type} {period_label} (id={report.id})")
        return _report_to_dict(report)

    finally:
        db.close()


def _report_to_dict(report: AnalyticsReport) -> dict:
    return {
        "id": report.id,
        "report_type": report.report_type,
        "period_start": report.period_start.isoformat(),
        "period_end": report.period_end.isoformat(),
        "period_label": report.period_label,
        "kpi": json.loads(report.kpi_json),
        "top_products": json.loads(report.top_products_json),
        "worst_products": json.loads(report.worst_products_json),
        "inventory": json.loads(report.inventory_json),
        "procurement": json.loads(report.procurement_json),
        "categories": json.loads(report.category_json),
        "buyer_countries": json.loads(report.buyer_country_json),
        "price_competitiveness": json.loads(report.price_competitiveness_json),
        "comparison": json.loads(report.comparison_json),
        "suggestions": json.loads(report.suggestions_json),
        "tool_suggestions": json.loads(report.tool_suggestions_json),
        "generated_at": report.generated_at.isoformat(),
    }


def get_report_list(report_type: str = "", limit: int = 20) -> list[dict]:
    """レポート一覧を取得"""
    db = get_db()
    try:
        q = db.query(AnalyticsReport)
        if report_type:
            q = q.filter(AnalyticsReport.report_type == report_type)
        reports = q.order_by(AnalyticsReport.period_start.desc()).limit(limit).all()
        return [
            {
                "id": r.id,
                "report_type": r.report_type,
                "period_label": r.period_label,
                "period_start": r.period_start.isoformat(),
                "period_end": r.period_end.isoformat(),
                "generated_at": r.generated_at.isoformat(),
                "kpi": json.loads(r.kpi_json),
            }
            for r in reports
        ]
    finally:
        db.close()


def get_report_by_id(report_id: int) -> dict | None:
    """IDでレポートを取得"""
    db = get_db()
    try:
        report = db.query(AnalyticsReport).filter(AnalyticsReport.id == report_id).first()
        if not report:
            return None
        return _report_to_dict(report)
    finally:
        db.close()


# ── スケジュール実行用 ────────────────────────────────────

def run_weekly_report():
    """週次レポート生成 + LINE通知（月曜実行）"""
    logger.info("Generating weekly report...")
    try:
        data = generate_report("weekly")
        kpi = data["kpi"]
        comp = data["comparison"]

        rev_change = comp.get("total_revenue_usd", {}).get("change_pct", 0)
        rev_arrow = "+" if rev_change >= 0 else ""

        lines = [
            "📊 eBay Agent — 週次分析レポート",
            f"📅 {data['period_label']}",
            "",
            f"💰 売上: ${kpi['total_revenue_usd']:,.2f} ({rev_arrow}{rev_change}%)",
            f"📈 利益: ${kpi['total_profit_usd']:,.2f}",
            f"📦 注文数: {kpi['total_orders']}件",
            f"📊 利益率: {kpi['avg_margin_pct']}%",
            "",
        ]

        # 改善提案サマリー
        suggestions = data.get("suggestions", [])
        high_priority = [s for s in suggestions if s.get("priority") == "high"]
        if high_priority:
            lines.append("⚠️ 要対応:")
            for s in high_priority[:3]:
                lines.append(f"  • {s['title']}")
            lines.append("")

        lines.append("📋 詳細はAgent Hub → Reports で確認")

        send_line_message("\n".join(lines))
        logger.info("Weekly report sent to LINE")
    except Exception as e:
        logger.exception(f"Weekly report generation failed: {e}")


def run_monthly_report():
    """月次レポート生成 + LINE通知（1日実行）"""
    logger.info("Generating monthly report...")
    try:
        data = generate_report("monthly")
        kpi = data["kpi"]
        comp = data["comparison"]

        rev_change = comp.get("total_revenue_usd", {}).get("change_pct", 0)
        rev_arrow = "+" if rev_change >= 0 else ""

        lines = [
            "📊 eBay Agent — 月次分析レポート",
            f"📅 {data['period_label']}",
            "",
            f"💰 月間売上: ${kpi['total_revenue_usd']:,.2f} ({rev_arrow}{rev_change}%)",
            f"📈 月間利益: ${kpi['total_profit_usd']:,.2f}",
            f"📦 月間注文: {kpi['total_orders']}件",
            f"📊 平均利益率: {kpi['avg_margin_pct']}%",
            f"💵 平均客単価: ${kpi['avg_order_value_usd']:,.2f}",
            "",
        ]

        # カテゴリTop3
        cats = data.get("categories", [])[:3]
        if cats:
            lines.append("🏷️ カテゴリTop3:")
            for c in cats:
                lines.append(f"  {c['category'][:20]}: ${c['revenue_usd']:,.2f}")
            lines.append("")

        # 改善提案
        suggestions = data.get("suggestions", [])
        if suggestions:
            lines.append(f"💡 改善提案 {len(suggestions)}件:")
            for s in suggestions[:3]:
                icon = "🔴" if s["priority"] == "high" else "🟡" if s["priority"] == "medium" else "🟢"
                lines.append(f"  {icon} {s['title']}")
            lines.append("")

        # ツール提案
        tools = data.get("tool_suggestions", [])[:2]
        if tools:
            lines.append("🛠️ ツール開発提案:")
            for t in tools:
                lines.append(f"  • {t['name']}")
            lines.append("")

        lines.append("📋 詳細はAgent Hub → Reports で確認")

        send_line_message("\n".join(lines))
        logger.info("Monthly report sent to LINE")
    except Exception as e:
        logger.exception(f"Monthly report generation failed: {e}")
