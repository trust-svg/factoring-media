"""チャットAIインテリジェンス — センチメント分析・スマートリプライ・バイヤースコアリング"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional

import anthropic
from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import BuyerMessage, SalesRecord

logger = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


# ── 1. センチメント分析 + 緊急度判定 ────────────────────

async def analyze_sentiment(message_body: str) -> dict:
    """メッセージのセンチメントと緊急度を分析する。

    Returns:
        {
            "sentiment": "positive" | "neutral" | "negative" | "angry",
            "urgency": "low" | "medium" | "high" | "critical",
            "note": "分析理由（日本語）"
        }
    """
    if not message_body.strip():
        return {"sentiment": "neutral", "urgency": "low", "note": ""}

    try:
        resp = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system="Analyze eBay buyer message sentiment and urgency. Reply ONLY with JSON.",
            messages=[{"role": "user", "content": f"""Analyze this eBay buyer message:

"{message_body}"

Return JSON:
{{"sentiment": "positive|neutral|negative|angry", "urgency": "low|medium|high|critical", "note": "理由を日本語で20文字以内"}}

Rules:
- angry: 明らかな不満・脅迫的表現
- critical: 返品期限間近・ケースオープン示唆・PayPal dispute言及
- high: 商品未着・破損報告・返金要求
- medium: 追跡番号確認・発送状況問い合わせ
- low: 一般的な質問・お礼"""}],
        )
        text = resp.content[0].text.strip()
        # JSON部分を抽出
        if "{" in text:
            text = text[text.index("{"):text.rindex("}") + 1]
        result = json.loads(text)
        return {
            "sentiment": result.get("sentiment", "neutral"),
            "urgency": result.get("urgency", "low"),
            "note": result.get("note", ""),
        }
    except Exception as e:
        logger.warning(f"センチメント分析エラー: {e}")
        return {"sentiment": "neutral", "urgency": "low", "note": ""}


# ── 2. スマートリプライ（ワンタップ返信候補3つ） ────────

async def get_smart_replies(message_body: str, context: str = "") -> List[str]:
    """メッセージに対する3つの返信候補を生成する。

    短い返信（1-2文）を3パターン:
    1. 丁寧・フォーマル
    2. フレンドリー・カジュアル
    3. 簡潔・最短
    """
    if not message_body.strip():
        return []

    try:
        resp = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system="""You are an eBay seller from Japan. Generate 3 short English reply options.
Each reply should be 1-2 sentences max.
Reply 1: Polite & formal
Reply 2: Friendly & warm
Reply 3: Brief & concise
Format: one reply per line, no numbering or labels.""",
            messages=[{"role": "user", "content": f"Buyer message:\n{message_body}\n{f'Context: {context}' if context else ''}"}],
        )
        lines = [l.strip() for l in resp.content[0].text.strip().split("\n") if l.strip()]
        return lines[:3]
    except Exception as e:
        logger.warning(f"スマートリプライ生成エラー: {e}")
        return []


# ── 3. バイヤースコアリング ──────────────────────────────

def get_buyer_score(db: Session, buyer_username: str) -> dict:
    """バイヤーをスコアリングする。

    Returns:
        {
            "tier": "vip" | "good" | "normal" | "caution",
            "total_orders": int,
            "total_spent_usd": float,
            "trouble_count": int,
            "avg_response_time_min": int | None,
            "last_order_date": str,
            "details": str  # 日本語の説明
        }
    """
    # 注文履歴を集計
    orders = db.query(SalesRecord).filter(
        SalesRecord.buyer_name == buyer_username
    ).all()

    total_orders = len(orders)
    total_spent = sum(o.sale_price_usd for o in orders)
    trouble_count = sum(
        1 for o in orders
        if o.progress in ("キャンセル", "返金", "cancelled", "refunded", "returned")
    )
    last_order = max((o.sold_at for o in orders), default=None)

    # メッセージ履歴から平均返信時間
    replied_msgs = db.query(BuyerMessage).filter(
        BuyerMessage.sender == buyer_username,
        BuyerMessage.direction == "inbound",
        BuyerMessage.response_time_min.isnot(None),
    ).all()
    avg_response = None
    if replied_msgs:
        times = [m.response_time_min for m in replied_msgs if m.response_time_min]
        avg_response = int(sum(times) / len(times)) if times else None

    # スコアリング
    if total_orders >= 3 and trouble_count == 0 and total_spent >= 100:
        tier = "vip"
        details = f"VIPバイヤー: {total_orders}回購入, ${total_spent:.0f}消費, トラブルなし"
    elif total_orders >= 2 and trouble_count == 0:
        tier = "good"
        details = f"優良バイヤー: {total_orders}回購入, トラブルなし"
    elif trouble_count >= 2 or (trouble_count > 0 and total_orders <= 1):
        tier = "caution"
        details = f"要注意: {trouble_count}回トラブル / {total_orders}回注文"
    else:
        tier = "normal"
        details = f"通常バイヤー: {total_orders}回注文"

    return {
        "tier": tier,
        "total_orders": total_orders,
        "total_spent_usd": round(total_spent, 2),
        "trouble_count": trouble_count,
        "avg_response_time_min": avg_response,
        "last_order_date": last_order.isoformat() if last_order else "",
        "details": details,
    }


# ── 4. 返信時間トラッキング ──────────────────────────────

def track_response_time(db: Session, buyer: str, item_id: str) -> None:
    """送信時に、直近のinboundメッセージの返信時間を記録する。"""
    last_inbound = db.query(BuyerMessage).filter(
        BuyerMessage.sender == buyer,
        BuyerMessage.item_id == item_id,
        BuyerMessage.direction == "inbound",
        BuyerMessage.replied_at.is_(None),
    ).order_by(BuyerMessage.received_at.desc()).first()

    if last_inbound and last_inbound.received_at:
        now = datetime.utcnow()
        delta = now - last_inbound.received_at
        minutes = int(delta.total_seconds() / 60)
        last_inbound.replied_at = now
        last_inbound.response_time_min = minutes
        db.commit()
        logger.info(f"返信時間記録: {buyer} → {minutes}分")


def get_response_time_stats(db: Session) -> dict:
    """全体の返信時間統計を取得する。"""
    msgs = db.query(BuyerMessage).filter(
        BuyerMessage.response_time_min.isnot(None),
        BuyerMessage.direction == "inbound",
    ).all()

    if not msgs:
        return {"avg_min": None, "median_min": None, "within_24h_pct": None, "total_tracked": 0}

    times = sorted([m.response_time_min for m in msgs if m.response_time_min is not None])
    avg = int(sum(times) / len(times))
    median = times[len(times) // 2]
    within_24h = sum(1 for t in times if t <= 1440)
    pct_24h = round(within_24h / len(times) * 100, 1)

    return {
        "avg_min": avg,
        "median_min": median,
        "within_24h_pct": pct_24h,
        "total_tracked": len(times),
    }


# ── 5. AI スタイル学習（過去返信から学習） ──────────────

async def generate_learned_draft(
    db: Session,
    message_body: str,
    buyer: str,
    item_id: str = "",
) -> str:
    """過去の送信メッセージを分析してスタイルを学習し、ドラフトを生成する。"""

    # 過去の送信メッセージを取得（最大20件）
    past_replies = db.query(BuyerMessage).filter(
        BuyerMessage.direction == "outbound",
    ).order_by(BuyerMessage.received_at.desc()).limit(20).all()

    style_examples = ""
    if past_replies:
        samples = past_replies[:10]
        style_examples = "\n--- Your past reply style examples ---\n"
        for r in samples:
            style_examples += f"Reply: {r.body[:200]}\n---\n"

    # 同じバイヤーとの過去のやり取り
    history = db.query(BuyerMessage).filter(
        (BuyerMessage.sender == buyer) | (BuyerMessage.recipient == buyer),
    ).order_by(BuyerMessage.received_at.desc()).limit(5).all()

    context = ""
    if history:
        context = "\n--- Recent conversation with this buyer ---\n"
        for h in reversed(history):
            direction = "Buyer" if h.direction == "inbound" else "You"
            context += f"{direction}: {h.body[:200]}\n"

    prompt = f"""Write a reply to this eBay buyer message.
Match the seller's writing style from the examples below.

Buyer message:
{message_body}
{context}
{style_examples}
---
Write a reply that sounds natural and matches the seller's usual style.
Reply in English only."""

    try:
        resp = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system="""You are an eBay seller's AI assistant. Your job is to write replies that match
the seller's personal communication style. Study the example replies carefully and mimic:
- Their greeting style
- Level of formality
- How they sign off
- Typical phrases they use
- How detailed their responses are

If no examples are available, use a professional but friendly tone.""",
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        logger.error(f"学習ドラフト生成エラー: {e}")
        return ""


# ── 6. 売上連携ビュー ───────────────────────────────────

def get_buyer_sales_info(db: Session, buyer_username: str, item_id: str = "") -> dict:
    """バイヤーの購入に関する売上・利益情報を取得する。"""
    query = db.query(SalesRecord).filter(SalesRecord.buyer_name == buyer_username)
    if item_id:
        query = query.filter(SalesRecord.item_id == item_id)

    records = query.order_by(SalesRecord.sold_at.desc()).all()

    orders = []
    for r in records:
        orders.append({
            "order_id": r.order_id,
            "item_id": r.item_id,
            "title": r.title,
            "sale_price_usd": r.sale_price_usd,
            "net_profit_usd": r.net_profit_usd,
            "net_profit_jpy": r.net_profit_jpy,
            "profit_margin_pct": r.profit_margin_pct,
            "source_cost_jpy": r.source_cost_jpy,
            "tracking_number": r.tracking_number,
            "shipping_method": r.shipping_method,
            "progress": r.progress,
            "sold_at": r.sold_at.isoformat() if r.sold_at else "",
            "marketplace": r.marketplace,
        })

    total_revenue = sum(r.sale_price_usd for r in records)
    total_profit = sum(r.net_profit_usd for r in records)

    return {
        "orders": orders,
        "total_orders": len(orders),
        "total_revenue_usd": round(total_revenue, 2),
        "total_profit_usd": round(total_profit, 2),
        "avg_profit_margin": round(
            sum(r.profit_margin_pct for r in records) / len(records), 1
        ) if records else 0,
    }
