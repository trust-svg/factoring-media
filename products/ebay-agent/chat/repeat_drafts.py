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


_SYSTEM_PROMPT = """You write 1:1 eBay buyer messages on behalf of "Samurai Shop Japan Select" (signed by Roki), a Japan-based eBay seller of audio gear, samurai armor, figures, watches, and other Japanese collectibles.

Audience: a past buyer who ALREADY received their item and ALREADY left positive Feedback. The item's safe arrival is established — do NOT speculate about it.

Your goal is to:
1. Open by thanking them for the kind feedback (not for the purchase, not "hoping it arrived safely").
2. Briefly reference one specific past item they bought.
3. Mention that Samurai Shop Japan Select sources Japanese collectibles regularly and can also search for specific items the buyer is looking for.
4. Invite them to tap "Save Seller" on the eBay store page to get new-arrival notifications.
5. Close warmly, inviting them to reach out anytime.

Hard rules:
- Output JSON via the submit_draft tool. NEVER reply in plain text.
- ENGLISH ONLY in the body field (body_ja is the Japanese translation).
- Total body ≤ 700 characters.
- Reference one specific past purchase (use the past_title provided).
- Do NOT use phrases like "I hope it arrived safely", "I hope you're enjoying it", "I hope it's in good condition", or "I hope it met your expectations" — these are odd given the buyer already left positive feedback.
- Include a soft offer to source specific items from Japan: e.g., "If there's anything specific you're looking for, please feel free to let me know — I'd be happy to keep an eye out."
- Recommend they tap "Save Seller" on the eBay store page to get new arrival alerts. Do NOT include any URL.
- No external URLs, no email addresses, no phone numbers.
- No mention of WhatsApp, Telegram, LINE, Instagram, Facebook, TikTok, WeChat, or any off-platform channel.
- Do NOT use pressure tactics ("act now", "hurry", "last chance", "limited time only").
- Warm, professional, slightly personal tone. Avoid emoji.
- The subject should be short (≤ 60 characters) and natural — no salesy capitalization.
- Sign off with exactly this 3-line signature:
    Best regards,
    Samurai Shop Japan Select
    Roki

Also include body_ja: a faithful, natural Japanese translation of the English body, written for a Japanese reviewer (not the buyer). Keep the same paragraph structure. Leave eBay-specific phrases like "Save Seller" in English inside Japanese quotes (e.g., 「Save Seller」). End the Japanese version with:
    敬具
    Samurai Shop Japan Select
    Roki
The body_ja is NEVER sent to the buyer — it's a review aid."""


_TOOL_DEFINITION = {
    "name": "submit_draft",
    "description": "Submit the eBay buyer message draft.",
    "input_schema": {
        "type": "object",
        "properties": {
            "subject": {
                "type": "string",
                "description": "Short message subject in English, ≤ 60 chars.",
            },
            "body": {
                "type": "string",
                "description": "Message body in English, ≤ 600 chars.",
            },
            "body_ja": {
                "type": "string",
                "description": "Faithful Japanese translation of body — for the Japanese reviewer to confirm tone and intent. NOT sent to the buyer. Translate naturally, do not literally translate eBay-specific phrases like 'Save Seller' (leave them in English in quotes).",
            },
            "rationale": {
                "type": "string",
                "description": "One short sentence in Japanese explaining tone choice (内部メモ・送信されない).",
            },
        },
        "required": ["subject", "body", "body_ja", "rationale"],
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
                        "subject": "Thank you for the kind feedback, collector_taro",
                        "body": "Hi collector_taro,\n\nThank you so much for the kind feedback on the Bandai S.H.Figuarts Gundam figure — it really means a lot.\n\nI source figures and Japanese collectibles from across Japan every week, and I'm always happy to keep an eye out for specific pieces. If there's a particular figure or series you're hunting for, please feel free to let me know.\n\nFor regular new-arrival alerts, you can tap \"Save Seller\" on my eBay store page.\n\nFeel free to reach out anytime.\n\nBest regards,\nSamurai Shop Japan Select\nRoki",
                        "body_ja": "collector_taroさん、こんにちは。\n\nバンダイ S.H.Figuarts のガンダムフィギュアにあたたかいフィードバックをいただき、本当にありがとうございます。とても嬉しく思います。\n\n当店では毎週、日本全国からフィギュアや日本のコレクター品を仕入れており、お探しの特定の作品やシリーズがあればお声がけください。喜んでお探しいたします。\n\n新着のお知らせを定期的に受け取りたい場合は、eBayストアページの「Save Seller」をタップしてください。\n\nご不明な点があればいつでもご連絡ください。\n\n敬具\nSamurai Shop Japan Select\nRoki",
                        "rationale": "コレクター層・短期リピート想定。フィードバック感謝で開き、リバースソーシング誘いとSave Seller誘導を自然に含める。",
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
                        "subject": "Thank you for the kind feedback, kenji_w",
                        "body": "Hi kenji_w,\n\nThank you for the kind feedback on the Seiko 5 Sports — it truly means a lot.\n\nI source watches one at a time from Japan, so each piece is a bit of a hunt. If there's a particular reference or model you've been looking for, please feel free to let me know — I'd be happy to keep an eye out.\n\nWhen the next interesting Seiko or vintage piece comes in, I'd love for you to see it first. To stay in the loop, please tap \"Save Seller\" on my store page and you'll be notified as new arrivals go live.\n\nFeel free to reach out anytime.\n\nBest regards,\nSamurai Shop Japan Select\nRoki",
                        "body_ja": "kenji_wさん、こんにちは。\n\nSeiko 5 Sports にあたたかいフィードバックをいただき、ありがとうございます。本当に励みになります。\n\n腕時計は日本から一点一点丁寧に仕入れているので、毎回が宝探しのようなものです。お探しの特定のリファレンスやモデルがあれば、お気軽にお声がけください。喜んでお探しいたします。\n\n次に良いSeikoやヴィンテージ品が入ったときは、まず一番にご覧いただきたいです。新着情報を逃さないよう、ストアページの「Save Seller」をタップしていただければ、入荷時にお知らせが届きます。\n\nご不明な点があればいつでもご連絡ください。\n\n敬具\nSamurai Shop Japan Select\nRoki",
                        "rationale": "高単価・長期フォロワー化方針。フィードバック感謝→希少性→リバースソーシング→Save Sellerの自然な流れ。",
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
                        "subject": "Thank you for your thoughtful feedback, armor_fan",
                        "body": "Hi armor_fan,\n\nThank you so much for the thoughtful feedback on the Edo-period Kabuto replica. It really means a lot, especially with a piece like that.\n\nOther armor and samurai-related items come up occasionally — they don't appear often, so each one is a bit special. If you have a particular type of helmet, mask, or armor piece you've been looking for, please feel free to let me know and I'll keep an eye out.\n\nTo be notified when a new piece is listed, please tap \"Save Seller\" on my eBay store page.\n\nFeel free to reach out anytime.\n\nBest regards,\nSamurai Shop Japan Select\nRoki",
                        "body_ja": "armor_fanさん、こんにちは。\n\n江戸時代の兜レプリカに、丁寧なフィードバックをいただきありがとうございます。このような品にお言葉をいただけて、本当に嬉しく思います。\n\n他の甲冑や侍関連の品も時折入荷しますが、頻繁に出るものではないので一点一点が特別です。お探しの兜・面・甲冑の種類などございましたら、お気軽にお声がけください。お探しいたします。\n\n新しい一点が出品された際にお知らせを受け取りたい場合は、eBayストアページの「Save Seller」をタップしてください。\n\nご不明な点があればいつでもご連絡ください。\n\n敬具\nSamurai Shop Japan Select\nRoki",
                        "rationale": "甲冑・希少性訴求。フィードバック感謝→希少性→リバースソーシング→Save Seller。長期フォロワー化を狙う。",
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
                body_ja = (data.get("body_ja") or "").strip()
                rationale = (data.get("rationale") or "")[:512]
                if not body:
                    return {
                        "subject": "",
                        "body": "",
                        "body_ja": "",
                        "rationale": "",
                        "error": "empty_body",
                    }
                return {
                    "subject": subject,
                    "body": body,
                    "body_ja": body_ja,
                    "rationale": rationale,
                }

        logger.warning(
            f"generate_draft: no tool_use block in response for buyer={buyer_username}"
        )
        return {
            "subject": "",
            "body": "",
            "body_ja": "",
            "rationale": "",
            "error": "no_tool_use",
        }

    except Exception as e:
        logger.exception(f"generate_draft crashed for buyer={buyer_username}")
        return {
            "subject": "",
            "body": "",
            "body_ja": "",
            "rationale": "",
            "error": str(e),
        }
