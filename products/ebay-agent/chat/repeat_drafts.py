"""リピート購入促進メッセージの Claude tool_use 下書き生成。

Anthropic Prompt Cache を活かす構造:
- 共通の system + tools 定義は cache_control を付けて長期キャッシュ
- user メッセージだけバイヤー名・過去商品タイトル等を差し替え

Phase 2 で 30 通の broadcast を流す時に効いてくる。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)


_CLIENT: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = anthropic.Anthropic()
    return _CLIENT


_SYSTEM_PROMPT = """You write 1:1 eBay buyer messages on behalf of SamuraiShopJapanSelect, a Japan-based eBay seller of audio gear, samurai armor, figures, watches, and other Japanese collectibles.

Audience: a past buyer who already received their item and left positive Feedback. Your goal is to thank them warmly, mention you have other items in stock they may like, and invite them to Save the seller so they get new-arrival notifications.

Hard rules:
- Output JSON via the submit_draft tool. NEVER reply in plain text.
- ENGLISH ONLY.
- Total body ≤ 600 characters.
- Reference one specific past purchase (use the past_title provided).
- Recommend they tap "Save Seller" on the eBay store page to get new arrival alerts. Do NOT include any URL.
- No external URLs, no email addresses, no phone numbers.
- No mention of WhatsApp, Telegram, LINE, Instagram, Facebook, TikTok, WeChat, or any off-platform channel.
- Do NOT use pressure tactics ("act now", "hurry", "last chance", "limited time only").
- Warm, professional tone. Avoid emoji.
- The subject should be short (≤ 60 characters) and natural — no salesy capitalization."""


_TOOL_DEFINITION = {
    "name": "submit_draft",
    "description": "Submit the eBay buyer message draft.",
    "input_schema": {
        "type": "object",
        "properties": {
            "subject": {
                "type": "string",
                "description": "Short message subject, ≤ 60 chars.",
            },
            "body": {
                "type": "string",
                "description": "Message body in English, ≤ 600 chars.",
            },
            "rationale": {
                "type": "string",
                "description": "One short sentence in Japanese explaining tone choice (内部メモ・送信されない).",
            },
        },
        "required": ["subject", "body", "rationale"],
    },
}


_FEW_SHOTS_BY_TAG: dict[str, list[dict]] = {
    "figure_collectible": [
        {
            "role": "user",
            "content": "buyer: collector_taro\npast_title: Bandai S.H.Figuarts Gundam Action Figure (mint)\ndelivered_days_ago: 9\nfeedback_comment: Beautiful packaging, arrived fast, thank you!\n\nWrite the draft.",
        },
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "demo_001",
                    "name": "submit_draft",
                    "input": {
                        "subject": "Thank you for the kind feedback",
                        "body": "Hi collector_taro,\n\nThank you so much for the warm feedback on the Bandai S.H.Figuarts Gundam figure — I'm really glad it arrived safely and that the packaging held up.\n\nI restock figures and Japanese collectibles every week, including some hard-to-find pieces. If you'd like to be notified when new arrivals go live, please tap \"Save Seller\" on my eBay store page.\n\nThanks again for your support!\n\nKind regards,\nSamuraiShopJapanSelect",
                        "rationale": "コレクター層・短期リピート想定。Save Seller誘導を自然な形で含める。",
                    },
                }
            ],
        },
    ],
    "watch_premium": [
        {
            "role": "user",
            "content": "buyer: kenji_w\npast_title: Seiko 5 Sports SRPD vintage\ndelivered_days_ago: 12\nfeedback_comment: Exactly as described. Will buy again.\n\nWrite the draft.",
        },
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "demo_002",
                    "name": "submit_draft",
                    "input": {
                        "subject": "Glad the Seiko found a good home",
                        "body": "Hi kenji_w,\n\nThank you for the kind feedback on the Seiko 5 Sports — it means a lot. I source watches carefully one at a time from Japan, so each piece is a bit of a hunt.\n\nWhen the next interesting Seiko or vintage piece comes in, I'd love for you to see it first. If you'd like to follow along, please tap \"Save Seller\" on my store page and you'll be notified as new arrivals go live.\n\nThanks again,\nSamuraiShopJapanSelect",
                        "rationale": "高単価・長期フォロワー化方針。一点物の希少さを示唆。",
                    },
                }
            ],
        },
    ],
    "armor_premium": [
        {
            "role": "user",
            "content": "buyer: armor_fan\npast_title: Edo period Samurai Kabuto helmet replica\ndelivered_days_ago: 11\nfeedback_comment: Stunning piece, packed with care.\n\nWrite the draft.",
        },
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "demo_003",
                    "name": "submit_draft",
                    "input": {
                        "subject": "Thank you for trusting the Kabuto to me",
                        "body": "Hi armor_fan,\n\nThank you so much for the thoughtful feedback on the Edo-period Kabuto replica. Pieces like that take time to source and prepare for shipment, and I'm really glad it arrived in the condition it deserved.\n\nI occasionally find other armor and samurai-related items — they don't come up often. If you'd like to be alerted when a new piece is listed, please tap \"Save Seller\" on my eBay store page.\n\nKind regards,\nSamuraiShopJapanSelect",
                        "rationale": "甲冑・希少性訴求。長期フォロワー化を狙う。",
                    },
                }
            ],
        },
    ],
}


def _build_messages(
    buyer_username: str,
    past_title: str,
    past_category_tag: str,
    delivered_at: Optional[datetime],
    feedback_comment: str,
) -> list[dict]:
    """few-shot + 当該リクエストの messages を組み立てる。"""
    delivered_days_ago = ""
    if delivered_at:
        delivered_days_ago = str(max(0, (datetime.utcnow() - delivered_at).days))

    msgs: list[dict] = []
    shots = (
        _FEW_SHOTS_BY_TAG.get(past_category_tag)
        or _FEW_SHOTS_BY_TAG["figure_collectible"]
    )
    msgs.extend(shots)

    # Anthropic API は assistant の tool_use の直後に tool_result が必要。
    # few-shot の最後の assistant ブロックから tool_use_id を取り出して
    # 同じ user ターン内で tool_result + 次リクエストを並べる。
    shot_tool_use_id = ""
    if shots and isinstance(shots[-1].get("content"), list):
        for block in shots[-1]["content"]:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                shot_tool_use_id = block.get("id", "")
                break

    user_payload = (
        f"buyer: {buyer_username}\n"
        f"past_title: {past_title or 'a Japanese collectible'}\n"
        f"delivered_days_ago: {delivered_days_ago or 'unknown'}\n"
        f"feedback_comment: {feedback_comment or '(no comment)'}\n\n"
        "Write the draft."
    )

    if shot_tool_use_id:
        msgs.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": shot_tool_use_id,
                        "content": "Draft accepted. Now write the next one.",
                    },
                    {"type": "text", "text": user_payload},
                ],
            }
        )
    else:
        msgs.append({"role": "user", "content": user_payload})
    return msgs


def generate_draft(
    buyer_username: str,
    past_title: str,
    past_category_tag: str = "other",
    delivered_at: Optional[datetime] = None,
    feedback_comment: str = "",
    model: str = "claude-sonnet-4-6",
) -> dict:
    """Claude tool_use で 1:1 メッセージ下書きを 1 件生成して返す。

    返値: {"subject": str, "body": str, "rationale": str}
    失敗時は body="" を含む dict を返す（呼び出し側で再試行/フォールバック判断）。
    """
    try:
        client = _get_client()
        resp = client.messages.create(
            model=model,
            max_tokens=800,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[
                {
                    **_TOOL_DEFINITION,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tool_choice={"type": "tool", "name": "submit_draft"},
            messages=_build_messages(
                buyer_username=buyer_username,
                past_title=past_title,
                past_category_tag=past_category_tag,
                delivered_at=delivered_at,
                feedback_comment=feedback_comment,
            ),
        )

        for block in resp.content:
            if (
                getattr(block, "type", None) == "tool_use"
                and block.name == "submit_draft"
            ):
                data = block.input or {}
                subject = (data.get("subject") or "")[:256]
                body = (data.get("body") or "").strip()
                rationale = (data.get("rationale") or "")[:512]
                if not body:
                    return {
                        "subject": "",
                        "body": "",
                        "rationale": "",
                        "error": "empty_body",
                    }
                return {"subject": subject, "body": body, "rationale": rationale}

        logger.warning(
            f"generate_draft: no tool_use block in response for buyer={buyer_username}"
        )
        return {"subject": "", "body": "", "rationale": "", "error": "no_tool_use"}

    except Exception as e:
        logger.exception(f"generate_draft crashed for buyer={buyer_username}")
        return {"subject": "", "body": "", "rationale": "", "error": str(e)}
