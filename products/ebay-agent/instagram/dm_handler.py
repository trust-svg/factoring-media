"""Instagram DM 自動返信・直接販売サポート

DM問合せの内容を解析し、在庫マッチング → 価格提示 → 返信ドラフト生成
"""
from __future__ import annotations

import json
import logging
import re

import anthropic

from database.models import get_db
from database import crud
from instagram.prompts import DM_REPLY_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# eBay手数料回避率（直接販売の割引率）
DIRECT_SALE_DISCOUNT = 0.87  # eBay価格 × 0.87


async def generate_dm_reply(
    dm_text: str,
    sender_name: str = "",
    context: str = "",
) -> dict:
    """
    DM問合せからAI返信ドラフトを生成する。

    Args:
        dm_text: DMメッセージ本文
        sender_name: 送信者名
        context: 追加コンテキスト（関連商品SKUなど）

    Returns:
        返信ドラフト + マッチング情報
    """
    db = get_db()
    try:
        # 在庫リストから関連商品を検索
        listings = crud.get_all_listings(db)
        inventory_summary = "\n".join(
            f"- SKU: {l.sku} | {l.title} | ${l.price_usd:.2f} | "
            f"Direct: ${l.price_usd * DIRECT_SALE_DISCOUNT:.2f} | "
            f"Stock: {l.quantity}"
            for l in listings[:100]  # 上限100件
        )

        client = anthropic.Anthropic()
        prompt = f"""Respond to this Instagram DM from a potential buyer.

SENDER: {sender_name or 'Unknown'}
MESSAGE: {dm_text}
{f'CONTEXT: {context}' if context else ''}

CURRENT INVENTORY (top items):
{inventory_summary}

Generate a helpful, sales-oriented reply. If they're asking about a specific product,
match it to our inventory and quote the direct purchase price (eBay price × {DIRECT_SALE_DISCOUNT}).

Respond with JSON only."""

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=DM_REPLY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return {"error": "AIの応答を解析できませんでした"}

        result = json.loads(match.group(0))

        return {
            "reply": result.get("reply", ""),
            "is_purchase_inquiry": result.get("is_purchase_inquiry", False),
            "matched_sku": result.get("matched_sku", ""),
            "suggested_price_usd": result.get("suggested_price_usd", 0.0),
            "language": result.get("language", "en"),
            "sender": sender_name,
            "original_message": dm_text,
            "note": "返信ドラフトです。送信前に内容を確認してください。",
        }
    finally:
        db.close()
