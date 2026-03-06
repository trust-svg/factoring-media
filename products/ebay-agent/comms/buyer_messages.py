"""バイヤーメッセージAI対応

eBay Trading API で受信したバイヤーメッセージに対して
Claude で返信ドラフトを生成する。
送信前に人間確認を必須とする。
"""
from __future__ import annotations

import logging

import anthropic

from ebay_core.client import get_buyer_messages

logger = logging.getLogger(__name__)

REPLY_SYSTEM_PROMPT = """あなたはeBayセラーのカスタマーサポートAIアシスタントです。

あなたの役割:
- バイヤーからのメッセージに対して、プロフェッショナルで丁寧な返信ドラフトを作成する
- 日本からの輸出セラーとしての立場を理解し、適切な対応をする

重要ルール:
1. 返信は必ず英語で作成する
2. 丁寧で親切なトーン
3. 具体的な情報を含める（追跡番号、到着予定、返品ポリシー等）
4. 問題がある場合は解決策を提示する
5. 「日本から発送」「丁寧な梱包」等の付加価値をさりげなく伝える

対応パターン:
- 商品の質問 → 正確な情報提供 + 追加写真の提案
- 発送状況の問い合わせ → 追跡情報 + 予想到着日
- 返品/返金リクエスト → ポリシー説明 + 解決策提案
- 値引き交渉 → 丁寧に断る or 条件付き承諾
- お礼/ポジティブ → 感謝 + リピート促進
"""


async def generate_reply_draft(message: dict) -> dict:
    """
    バイヤーメッセージに対するAI返信ドラフトを生成する。

    Args:
        message: バイヤーメッセージ辞書
            {sender, subject, body, item_id, ...}

    Returns:
        {
            "message_id": str,
            "sender": str,
            "subject": str,
            "original_body": str,
            "draft_reply": str,
            "tone": str,
            "category": str,
            "status": "draft",
        }
    """
    client = anthropic.Anthropic()

    prompt = f"""以下のeBayバイヤーメッセージに対する返信ドラフトを作成してください。

FROM: {message.get('sender', 'unknown')}
SUBJECT: {message.get('subject', 'No subject')}
ITEM ID: {message.get('item_id', 'N/A')}

MESSAGE:
{message.get('body', '')}

---
返信ドラフトを英語で作成し、以下のJSON形式で返してください:
{{"reply": "返信本文", "tone": "friendly/professional/apologetic", "category": "question/shipping/return/negotiation/thanks/other"}}
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=REPLY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    reply_text = response.content[0].text
    # JSONパース試行
    import json
    try:
        parsed = json.loads(reply_text)
        draft_reply = parsed.get("reply", reply_text)
        tone = parsed.get("tone", "professional")
        category = parsed.get("category", "other")
    except (json.JSONDecodeError, KeyError):
        draft_reply = reply_text
        tone = "professional"
        category = "other"

    return {
        "message_id": message.get("message_id", ""),
        "sender": message.get("sender", ""),
        "subject": message.get("subject", ""),
        "original_body": message.get("body", ""),
        "draft_reply": draft_reply,
        "tone": tone,
        "category": category,
        "status": "draft",
    }


async def process_unread_messages(days: int = 7) -> dict:
    """
    未読メッセージを一括取得し、返信ドラフトを生成する。

    Returns:
        {
            "total_messages": int,
            "unread": int,
            "drafts_generated": int,
            "drafts": list[dict],
        }
    """
    messages = get_buyer_messages(days=days)

    unread = [m for m in messages if not m["is_read"] and not m["responded"]]

    drafts = []
    for msg in unread[:10]:  # 一度に最大10件
        try:
            draft = await generate_reply_draft(msg)
            drafts.append(draft)
        except Exception as e:
            logger.warning(f"Draft generation failed for msg {msg.get('message_id')}: {e}")

    return {
        "total_messages": len(messages),
        "unread": len(unread),
        "drafts_generated": len(drafts),
        "drafts": drafts,
    }
