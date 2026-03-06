"""需要検知モジュール

eBay のアクティブ出品データから売れ筋度を分析し、
日本マーケットプレイスとの価格差から利益が出る商品をランク付けする。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from config import EBAY_FEE_RATE
from ebay_core.client import search_ebay, search_ebay_sold
from ebay_core.exchange_rate import get_usd_to_jpy

logger = logging.getLogger(__name__)


@dataclass
class DemandResult:
    """需要分析結果"""
    query: str
    items_found: int
    avg_price_usd: float
    min_price_usd: float
    max_price_usd: float
    top_sellers: list[dict]
    sell_through_score: float  # 0-100: 売れ筋度
    estimated_margin_pct: float  # 推定利益率
    source_price_jpy: int  # 推定仕入れ価格
    recommendation: str


def analyze_demand(
    query: str,
    max_source_price_jpy: int = 50000,
    limit: int = 50,
    category_id: str = "",
) -> dict:
    """
    指定カテゴリ/キーワードの需要を分析する。

    1. Browse API でアクティブ出品を検索
    2. 販売数量(soldQuantity)で売れ筋度を算出
    3. 推定仕入れ価格と比較して利益率を計算
    4. 有望商品リストを返す

    Args:
        query: 検索キーワード（英語）
        max_source_price_jpy: 仕入れ上限（円）
        limit: 検索件数上限
        category_id: eBayカテゴリID（オプション）

    Returns:
        需要分析結果の辞書
    """
    # アクティブ出品検索
    active_items = search_ebay(query, limit=limit, category_id=category_id)
    if not active_items:
        return {
            "query": query,
            "status": "no_results",
            "message": f"「{query}」の出品が見つかりませんでした",
            "items_found": 0,
        }

    # 売れ筋データ取得
    sold_items = search_ebay_sold(query, limit=limit, category_id=category_id)

    # 価格分析
    prices = [i["price"] for i in active_items if i["price"] > 0]
    if not prices:
        return {
            "query": query,
            "status": "no_price_data",
            "message": "価格データが取得できませんでした",
            "items_found": len(active_items),
        }

    avg_price = sum(prices) / len(prices)
    min_price = min(prices)
    max_price = max(prices)
    median_price = sorted(prices)[len(prices) // 2]

    # 売れ筋度スコア計算
    total_sold = sum(i.get("sold_quantity", 0) for i in sold_items)
    active_count = len(active_items)
    # 売れた数量÷出品数でスコア算出（上限100）
    sell_through = min(100, (total_sold / max(active_count, 1)) * 20)

    # 利益率推定
    rate = get_usd_to_jpy()
    # 仕入れ価格は販売価格の40-60%を仮定（日本→海外マージン）
    estimated_source_jpy = int(median_price * rate * 0.4)
    shipping_jpy = 2000  # 推定送料
    total_cost_jpy = estimated_source_jpy + shipping_jpy
    total_cost_usd = total_cost_jpy / rate
    ebay_fees = median_price * EBAY_FEE_RATE
    estimated_profit = median_price - total_cost_usd - ebay_fees
    estimated_margin = (estimated_profit / median_price * 100) if median_price > 0 else 0

    # トップセラー分析（よく売れている出品者）
    seller_counts: dict[str, int] = {}
    for item in active_items:
        seller = item.get("seller", "unknown")
        seller_counts[seller] = seller_counts.get(seller, 0) + 1
    top_sellers = [
        {"seller": s, "listings": c}
        for s, c in sorted(seller_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    ]

    # 推奨判定
    if sell_through >= 60 and estimated_margin > 20:
        recommendation = "★★★ 強く推奨: 高需要・高利益率"
    elif sell_through >= 40 and estimated_margin > 15:
        recommendation = "★★ 推奨: 需要あり・利益率良好"
    elif sell_through >= 20 and estimated_margin > 10:
        recommendation = "★ 検討可: 一定の需要あり"
    elif estimated_margin < 5:
        recommendation = "△ 非推奨: 利益率が低い"
    else:
        recommendation = "○ 条件次第: 仕入れ価格による"

    # 有望アイテム（売れ筋+利益率を考慮してソート）
    promising_items = []
    for item in sold_items[:20]:
        item_price = item.get("price", 0)
        item_sold = item.get("sold_quantity", 0)
        if item_price > 0 and item_sold > 0:
            item_source_est = int(item_price * rate * 0.4)
            item_cost_usd = (item_source_est + shipping_jpy) / rate
            item_profit = item_price - item_cost_usd - (item_price * EBAY_FEE_RATE)
            item_margin = item_profit / item_price * 100

            promising_items.append({
                "title": item["title"],
                "price_usd": item_price,
                "sold_quantity": item_sold,
                "estimated_margin_pct": round(item_margin, 1),
                "estimated_source_jpy": item_source_est,
                "item_url": item.get("item_url", ""),
                "category_id": item.get("category_id", ""),
            })

    # マージン順でソート
    promising_items.sort(
        key=lambda x: x["sold_quantity"] * x["estimated_margin_pct"],
        reverse=True,
    )

    return {
        "query": query,
        "status": "success",
        "items_found": len(active_items),
        "price_analysis": {
            "avg_usd": round(avg_price, 2),
            "min_usd": round(min_price, 2),
            "max_usd": round(max_price, 2),
            "median_usd": round(median_price, 2),
        },
        "demand_score": round(sell_through, 1),
        "total_sold_qty": total_sold,
        "estimated_margin_pct": round(estimated_margin, 1),
        "estimated_source_jpy": estimated_source_jpy,
        "exchange_rate": rate,
        "recommendation": recommendation,
        "top_sellers": top_sellers,
        "promising_items": promising_items[:10],
    }


def compare_categories(queries: list[str], limit: int = 30) -> dict:
    """
    複数カテゴリ/キーワードを比較分析する。

    Args:
        queries: 比較するキーワードリスト
        limit: 各検索の件数上限

    Returns:
        カテゴリ比較結果
    """
    results = []
    for query in queries:
        try:
            analysis = analyze_demand(query, limit=limit)
            results.append(analysis)
        except Exception as e:
            logger.warning(f"Category analysis failed for '{query}': {e}")
            results.append({
                "query": query,
                "status": "error",
                "message": str(e),
            })

    # スコア順でソート
    successful = [r for r in results if r.get("status") == "success"]
    successful.sort(
        key=lambda r: r.get("demand_score", 0) * max(r.get("estimated_margin_pct", 0), 0),
        reverse=True,
    )

    return {
        "total_categories": len(queries),
        "successful_analyses": len(successful),
        "rankings": [
            {
                "rank": i + 1,
                "query": r["query"],
                "demand_score": r["demand_score"],
                "estimated_margin_pct": r["estimated_margin_pct"],
                "items_found": r["items_found"],
                "recommendation": r["recommendation"],
            }
            for i, r in enumerate(successful)
        ],
        "details": results,
    }
