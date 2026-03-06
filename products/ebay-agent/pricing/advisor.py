"""AI 価格アドバイザー

Claude を使って価格提案を生成する。
入力: 現在価格 + 競合価格 + 為替レート + 価格履歴
出力: 推奨価格 + 理由 + 利益率予測
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import anthropic

from config import EBAY_FEE_RATE
from database.models import get_db
from database import crud
from ebay_core.exchange_rate import get_usd_to_jpy

logger = logging.getLogger(__name__)

PRICING_SYSTEM_PROMPT = """You are an expert eBay pricing strategist for Japanese exports.
Analyze the provided data and recommend an optimal price.

Consider:
1. Competitor pricing (average, min, max)
2. Current price position relative to competitors
3. Price history trends
4. eBay fee impact (12.9% final value fee)
5. Exchange rate (USD→JPY) for margin calculation
6. Market demand signals (number of competitors)

Rules:
- Never recommend pricing below the lowest competitor unless there's a strategic reason
- Factor in the "Japan quality" premium (authentic Japanese products can command 5-15% premium)
- If our price is already competitive (within ±5% of average), suggest keeping it
- Always provide a clear reasoning in Japanese
- Return results using the provided tool
"""

PRICING_TOOL = {
    "name": "price_recommendation",
    "description": "Submit a price recommendation with reasoning",
    "input_schema": {
        "type": "object",
        "properties": {
            "recommended_price_usd": {
                "type": "number",
                "description": "Recommended price in USD",
            },
            "action": {
                "type": "string",
                "enum": ["raise", "lower", "keep"],
                "description": "Recommended action",
            },
            "confidence": {
                "type": "number",
                "description": "Confidence level 0.0-1.0",
            },
            "reasoning_ja": {
                "type": "string",
                "description": "Reasoning in Japanese",
            },
            "expected_margin_pct": {
                "type": "number",
                "description": "Expected profit margin percentage if source cost is known",
            },
        },
        "required": ["recommended_price_usd", "action", "confidence", "reasoning_ja"],
    },
}


async def get_price_advice(
    sku: str,
    source_cost_jpy: Optional[int] = None,
) -> dict:
    """
    指定SKUの価格アドバイスをAIで生成。

    Args:
        sku: 対象SKU
        source_cost_jpy: 仕入れ原価（円）がわかっている場合

    Returns:
        {
            "sku": str,
            "current_price": float,
            "recommended_price": float,
            "action": "raise" | "lower" | "keep",
            "confidence": float,
            "reasoning": str,
            "expected_margin_pct": float | None,
            "competitor_summary": dict,
            "price_history_trend": str,
        }
    """
    db = get_db()
    try:
        listing = crud.get_listing(db, sku)
        if not listing:
            return {"error": f"SKU {sku} が見つかりません"}

        # 価格履歴
        history = crud.get_price_history(db, sku, days=30)
        rate = get_usd_to_jpy()

        # 最新の競合データ
        latest = history[0] if history else None
        if not latest:
            return {"error": f"SKU {sku} の価格データがありません。先に analyze_pricing を実行してください。"}

        # 価格トレンド分析
        trend = "stable"
        if len(history) >= 2:
            recent_avg = history[0].avg_competitor_price_usd
            older_avg = history[-1].avg_competitor_price_usd
            if older_avg > 0:
                change_pct = (recent_avg - older_avg) / older_avg * 100
                if change_pct > 5:
                    trend = "rising"
                elif change_pct < -5:
                    trend = "falling"

        # プロンプト構築
        prompt = f"""Analyze pricing for this eBay listing:

**Product**: {listing.title}
**SKU**: {sku}
**Current Price**: ${listing.price_usd:.2f}
**Quantity**: {listing.quantity}

**Latest Competitor Data**:
- Average Price: ${latest.avg_competitor_price_usd:.2f}
- Lowest Price: ${latest.lowest_competitor_price_usd:.2f}
- Number of Competitors: {latest.num_competitors}
- Our Price vs Average: {((listing.price_usd - latest.avg_competitor_price_usd) / latest.avg_competitor_price_usd * 100):.1f}%

**Price Trend** (30 days): {trend}
**Exchange Rate**: 1 USD = ¥{rate:.1f}
**eBay Fee Rate**: {EBAY_FEE_RATE * 100}%
"""

        if source_cost_jpy:
            cost_usd = source_cost_jpy / rate
            current_margin = (listing.price_usd - listing.price_usd * EBAY_FEE_RATE - cost_usd) / listing.price_usd * 100
            prompt += f"""
**Source Cost**: ¥{source_cost_jpy:,} (${cost_usd:.2f})
**Current Margin**: {current_margin:.1f}%
"""

        if len(history) > 1:
            prompt += "\n**Price History**:\n"
            for h in history[:5]:
                prompt += f"  - {h.recorded_at.strftime('%m/%d')}: Avg ${h.avg_competitor_price_usd:.2f}, Low ${h.lowest_competitor_price_usd:.2f}, Ours ${h.our_price_usd:.2f}\n"

        prompt += "\nPlease provide your price recommendation."

        # Claude API 呼び出し
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            system=PRICING_SYSTEM_PROMPT,
            tools=[PRICING_TOOL],
            messages=[{"role": "user", "content": prompt}],
        )

        # ツール呼び出し結果を抽出
        result = {
            "sku": sku,
            "current_price": listing.price_usd,
            "recommended_price": listing.price_usd,
            "action": "keep",
            "confidence": 0.5,
            "reasoning": "",
            "expected_margin_pct": None,
            "competitor_summary": {
                "avg": latest.avg_competitor_price_usd,
                "min": latest.lowest_competitor_price_usd,
                "count": latest.num_competitors,
            },
            "price_history_trend": trend,
        }

        for block in response.content:
            if block.type == "tool_use" and block.name == "price_recommendation":
                inp = block.input
                result["recommended_price"] = inp["recommended_price_usd"]
                result["action"] = inp["action"]
                result["confidence"] = inp["confidence"]
                result["reasoning"] = inp["reasoning_ja"]
                if "expected_margin_pct" in inp:
                    result["expected_margin_pct"] = inp["expected_margin_pct"]

        # DB に最適化提案として記録
        if result["action"] != "keep":
            crud.add_optimization(
                db,
                sku=sku,
                original_title=listing.title,
                suggested_title=listing.title,
                original_description=f"Price: ${listing.price_usd:.2f}",
                suggested_description=f"Price: ${result['recommended_price']:.2f} ({result['action']})",
                reasoning=result["reasoning"],
                confidence=result["confidence"],
            )

        return result
    finally:
        db.close()


async def batch_price_advice(limit: int = 10) -> dict:
    """
    価格差が大きい出品に対して一括でAI価格提案を生成。

    Returns:
        {
            "total_analyzed": int,
            "recommendations": list[dict],
            "raise_count": int,
            "lower_count": int,
            "keep_count": int,
        }
    """
    db = get_db()
    try:
        # 最新の価格履歴から差が大きいものを抽出
        from sqlalchemy import desc, func
        from database.models import PriceHistory

        # SKU毎に最新レコードを取得
        subq = (
            db.query(
                PriceHistory.sku,
                func.max(PriceHistory.id).label("max_id"),
            )
            .group_by(PriceHistory.sku)
            .subquery()
        )

        latest_prices = (
            db.query(PriceHistory)
            .join(subq, PriceHistory.id == subq.c.max_id)
            .all()
        )

        # 価格差が大きい順にソート
        candidates = []
        for ph in latest_prices:
            if ph.avg_competitor_price_usd > 0:
                diff = abs(ph.our_price_usd - ph.avg_competitor_price_usd) / ph.avg_competitor_price_usd * 100
                if diff > 5:  # 5%以上の差があるもの
                    candidates.append((ph.sku, diff))

        candidates.sort(key=lambda x: x[1], reverse=True)
        target_skus = [sku for sku, _ in candidates[:limit]]
    finally:
        db.close()

    recommendations = []
    for sku in target_skus:
        try:
            result = await get_price_advice(sku)
            if "error" not in result:
                recommendations.append(result)
        except Exception as e:
            logger.warning(f"Price advice failed for {sku}: {e}")

    raise_count = sum(1 for r in recommendations if r["action"] == "raise")
    lower_count = sum(1 for r in recommendations if r["action"] == "lower")
    keep_count = sum(1 for r in recommendations if r["action"] == "keep")

    return {
        "total_analyzed": len(recommendations),
        "recommendations": recommendations,
        "raise_count": raise_count,
        "lower_count": lower_count,
        "keep_count": keep_count,
    }
