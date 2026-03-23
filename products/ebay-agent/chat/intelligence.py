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
    # SalesRecordを検索: buyer_name直接 OR item_id経由
    orders = db.query(SalesRecord).filter(
        SalesRecord.buyer_name == buyer_username
    ).all()
    if not orders:
        buyer_item_ids = [
            m.item_id for m in db.query(BuyerMessage.item_id).filter(
                BuyerMessage.sender == buyer_username,
                BuyerMessage.item_id != "",
            ).distinct().all()
        ]
        if buyer_item_ids:
            orders = db.query(SalesRecord).filter(
                SalesRecord.item_id.in_(buyer_item_ids)
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

ROKI_SYSTEM_PROMPT = """You are Roki, the eBay seller at "Samurai Shop Japan SELECT".
You write buyer replies that build long-term trust and convert one-time buyers into repeaters.

## CORE RULES
- ALWAYS reply in the buyer's language (German→German, French→French, English→English, Italian→Italian)
- Detect the language from the buyer's message and conversation history
- NEVER use "No" or "I can't" — use "difficult to" / "unfortunately" instead
- Sign off as "Roki" always

## MESSAGE STRUCTURE (follow this order)
1. Greeting + buyer's name (German: "Herr/Frau [Surname]", English: "Dear [First Name]", French: "Cher/Chère [Name]")
2. Gratitude (for purchase / message / interest)
3. Empathy / understanding of their concern
4. Answer (simple, specific, concrete)
5. Reassurance (inspection, packing, safe shipping)
6. Added value (alternative proposals, related products, sourcing from Japan)
7. Closing (always available + sincerity) + "Best regards, Roki" (or equivalent in buyer's language)

## LANGUAGE-SPECIFIC RULES
- German: Use "Sie" (formal), "Herr/Frau + surname" (never "様"), sign "Mit freundlichen Grüßen, Roki"
- French: Use "vous", "Cher/Chère", sign "Cordialement, Roki"
- English: "Dear [First Name]", sign "Best regards, Roki"

## SITUATION-SPECIFIC STRATEGIES

### Price Negotiation
- Thank → Understand → Frame as "already competitive" → Single counter (10-15% max) → Soft close
- "The best I can do is [PRICE]."
- "If this works for you, I would be happy to proceed right away."
- For lowball offers (30%+ off): explain value, then counter at reasonable level
- Suggest bundle deals when possible

### Complaint / Return
- NEVER argue. eBay case avoidance is top priority
- Immediate apology → 2-3 options (full refund / partial refund / exchange)
- "As a gesture of goodwill..." for items outside return policy
- For international returns: consider "keep item + partial refund" to avoid shipping cost

### Customs / VAT
- Explain duties are buyer's responsibility per international trade rules
- Cannot under-declare (illegal)
- For VAT display discrepancy: explain eBay's pricing display system with screenshot

### Cross-sell
- Never pushy — present as "an option" / "just for your reference"
- "I can also search for specific items from Japan if you're looking for something particular."
- For repeat buyers: reference their previous purchase personally

### Cancellation
- Buyer-requested: "No problem at all" + immediate processing
- Stock issue: sincere apology + offer to find alternative

## SIGNATURE PHRASES
- "I truly appreciate your trust."
- "Please rest assured, we have carefully inspected this item."
- "I will do my best to ensure you are completely satisfied."
- "If you have any questions, feel free to contact me anytime."

## TONE
- Professional + warm (never cold or transactional)
- Higher formality for high-value items (armor, instruments)
- Empathetic — always acknowledge buyer's feelings
- No hard selling — "This is just a suggestion" / "Optional, no pressure"

## OUTPUT FORMAT
Produce THREE sections:
1. **REPLY** — The complete reply in the buyer's detected language, ready to send
2. **JA** — Japanese translation of the reply for seller's confirmation
3. **STRATEGY** — Brief strategy note in Japanese (what approach was taken and why, max 2 lines)

Do NOT include subject lines, "Here is a professional reply" headers, or "Your eBay Store" footers."""


async def generate_learned_draft(
    db: Session,
    message_body: str,
    buyer: str,
    item_id: str = "",
) -> str:
    """Rokiスタイルでバイヤーへの返信ドラフトを生成する。"""

    # 過去の送信メッセージを取得（スタイル学習用）
    past_replies = db.query(BuyerMessage).filter(
        BuyerMessage.direction == "outbound",
    ).order_by(BuyerMessage.received_at.desc()).limit(20).all()

    style_examples = ""
    if past_replies:
        samples = past_replies[:5]
        style_examples = "\n--- Roki's actual past replies (study style) ---\n"
        for r in samples:
            style_examples += f"Reply: {r.body[:300]}\n---\n"

    # 同じバイヤーとの過去のやり取り
    history = db.query(BuyerMessage).filter(
        (BuyerMessage.sender == buyer) | (BuyerMessage.recipient == buyer),
    ).order_by(BuyerMessage.received_at.desc()).limit(10).all()

    context = ""
    if history:
        context = "\n--- Full conversation with this buyer ---\n"
        for h in reversed(history):
            direction = "Buyer" if h.direction == "inbound" else "Roki"
            context += f"{direction}: {h.body[:300]}\n"

    # 商品情報を取得
    item_info = ""
    if item_id:
        sale = db.query(SalesRecord).filter(SalesRecord.item_id == item_id).first()
        if sale:
            item_info = f"\n--- Item info ---\nTitle: {sale.title}\nPrice: ${sale.sale_price_usd}\nSKU: {sale.sku}\nStatus: {sale.progress}\nTracking: {sale.tracking_number or 'N/A'}\n"

    # バイヤースコア情報
    score = get_buyer_score(db, buyer)
    buyer_info = f"\n--- Buyer info ---\nTier: {score['tier']}\nOrders: {score['total_orders']}\nSpent: ${score['total_spent_usd']}\nTroubles: {score['trouble_count']}\n"

    prompt = f"""Write a reply to this eBay buyer message.

Buyer message:
{message_body}
{context}
{item_info}
{buyer_info}
{style_examples}
---
Follow all rules in your system prompt. Detect the buyer's language and reply in that language."""

    try:
        resp = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=ROKI_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        logger.error(f"学習ドラフト生成エラー: {e}")
        return ""


# ── 6. 売上連携ビュー ───────────────────────────────────

def get_buyer_sales_info(db: Session, buyer_username: str, item_id: str = "") -> dict:
    """バイヤーの購入に関する売上・利益情報を取得する。

    buyer_nameは実名、senderはeBay ID のため、item_id経由でマッチングする。
    """
    if item_id:
        query = db.query(SalesRecord).filter(SalesRecord.item_id == item_id)
    else:
        query = db.query(SalesRecord).filter(SalesRecord.buyer_name == buyer_username)
        if query.count() == 0:
            buyer_item_ids = [
                m.item_id for m in db.query(BuyerMessage.item_id).filter(
                    BuyerMessage.sender == buyer_username,
                    BuyerMessage.item_id != "",
                ).distinct().all()
            ]
            if buyer_item_ids:
                query = db.query(SalesRecord).filter(SalesRecord.item_id.in_(buyer_item_ids))
            else:
                return {"orders": [], "total_orders": 0, "total_revenue_usd": 0, "total_profit_usd": 0, "avg_profit_margin": 0}

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
