"""リピート購入エンジン用 Telegram 承認カード。

`comms/dropship_notify.py:send_telegram` は通常テキストのみだが、
ここでは inline_keyboard を持つ sendMessage と callback_query パースを担当する。

承認カードのフロー:
  1. send_approval_card(offer_id) → Telegram に ✅Send / ❌Skip / ✏️Edit カード
  2. ユーザーがボタンを押すと callback_query が POST /webhook/telegram に届く
  3. parse_callback_query() で action と offer_id を取り出し、
     chat.repeat_engine.handle_telegram_action(action, offer_id, cb) を呼ぶ
"""

from __future__ import annotations

import html
import json
import logging
from typing import Optional

import httpx

from config import (
    REPEAT_ENGINE_DRY_RUN,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)
from database.models import OutboundOffer, SalesRecord, get_db

logger = logging.getLogger(__name__)


_API_BASE = "https://api.telegram.org"


def _build_keyboard(offer_id: int) -> dict:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Send",
                    "callback_data": f"ro:approve:{offer_id}",
                },
                {
                    "text": "❌ Skip",
                    "callback_data": f"ro:reject:{offer_id}",
                },
                {
                    "text": "✏️ Edit",
                    "callback_data": f"ro:edit:{offer_id}",
                },
            ]
        ]
    }


def _format_card(offer: OutboundOffer, sale: Optional[SalesRecord]) -> str:
    dry_run_prefix = "[DRY-RUN] " if REPEAT_ENGINE_DRY_RUN else ""
    flags = []
    try:
        flags = json.loads(offer.compliance_flags_json or "[]")
    except Exception:
        flags = []

    block_flags = [f for f in flags if f.startswith("block:")]
    warn_flags = [f for f in flags if f.startswith("warn:")]

    past_title = sale.title[:80] if sale and sale.title else "(unknown)"
    past_item_id = offer.past_order_item_id or "(none)"

    lines = [
        f"<b>{dry_run_prefix}🔁 Repeat Engine — Approval</b>",
        f"buyer: <code>{html.escape(offer.buyer_username)}</code>",
        f"trigger: <code>{html.escape(offer.trigger)}</code>",
        f"past_item: <code>{html.escape(past_item_id)}</code> — {html.escape(past_title)}",
        "",
        f"<b>Subject:</b> {html.escape(offer.draft_subject or '(none)')}",
        "",
        "<b>Body (English — sent to buyer):</b>",
        f"<pre>{html.escape(offer.draft_body or '(empty)')}</pre>",
    ]
    if offer.draft_body_ja:
        lines.append("")
        lines.append("<b>🇯🇵 日本語訳（確認用・送信されない）:</b>")
        lines.append(f"<pre>{html.escape(offer.draft_body_ja)}</pre>")
    if block_flags:
        lines.append("")
        lines.append("⛔ <b>BLOCKED — manual edit required</b>")
        lines.append(", ".join(html.escape(f) for f in block_flags))
    if warn_flags:
        lines.append("")
        lines.append("⚠️ warnings: " + ", ".join(html.escape(f) for f in warn_flags))
    if offer.draft_rationale:
        lines.append("")
        lines.append(f"<i>note: {html.escape(offer.draft_rationale[:200])}</i>")
    return "\n".join(lines)


async def send_approval_card(offer_id: int) -> dict:
    """指定の outbound_offer について Telegram 承認カードを送る。

    戻り値: {"sent": bool, "message_id": int | None}
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials missing — approval card skipped")
        return {"sent": False, "error": "no_credentials"}

    db = get_db()
    try:
        offer = db.query(OutboundOffer).filter(OutboundOffer.id == offer_id).first()
        if offer is None:
            return {"sent": False, "error": "offer_not_found"}
        sale = None
        if offer.past_sale_record_id:
            sale = (
                db.query(SalesRecord)
                .filter(SalesRecord.id == offer.past_sale_record_id)
                .first()
            )

        text = _format_card(offer, sale)
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": _build_keyboard(offer.id),
        }

        url = f"{_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=15)
        if resp.status_code != 200:
            logger.error(
                f"Telegram approval card failed: {resp.status_code} {resp.text[:300]}"
            )
            return {"sent": False, "error": f"http_{resp.status_code}"}

        body = resp.json()
        msg_id = (body.get("result") or {}).get("message_id")
        chat_id = ((body.get("result") or {}).get("chat") or {}).get("id")
        offer.telegram_message_id = msg_id
        offer.telegram_chat_id = chat_id
        db.commit()
        return {"sent": True, "message_id": msg_id}
    except Exception as e:
        logger.exception(f"send_approval_card crashed offer={offer_id}")
        db.rollback()
        return {"sent": False, "error": str(e)}
    finally:
        db.close()


def parse_callback_query(update: dict) -> Optional[dict]:
    """Telegram update から callback_query をパースする。

    `ro:<action>:<offer_id>` 形式の callback_data のみ受け付ける。
    それ以外は None を返す。
    """
    cb = update.get("callback_query")
    if not cb:
        return None
    data = cb.get("data") or ""
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "ro":
        return None
    action = parts[1]
    try:
        offer_id = int(parts[2])
    except ValueError:
        return None
    return {
        "action": action,
        "offer_id": offer_id,
        "callback_query_id": cb.get("id"),
        "from": cb.get("from") or {},
        "message": cb.get("message") or {},
    }


async def answer_callback_query(callback_query_id: str, text: str = "") -> None:
    """Telegram のローディングインジケータを止める。失敗しても無視する。"""
    if not TELEGRAM_BOT_TOKEN or not callback_query_id:
        return
    try:
        url = f"{_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
        payload = {"callback_query_id": callback_query_id, "text": text[:200]}
        async with httpx.AsyncClient() as client:
            await client.post(url, json=payload, timeout=10)
    except Exception:
        logger.exception("answer_callback_query failed")


async def edit_card_status(chat_id: int, message_id: int, status_line: str) -> None:
    """承認後のフィードバック表示として、カード末尾に状態を追記する。"""
    if not TELEGRAM_BOT_TOKEN or not chat_id or not message_id:
        return
    try:
        url = f"{_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/editMessageReplyMarkup"
        # ボタンを外す（reply_markup 省略で外せる）
        payload = {"chat_id": chat_id, "message_id": message_id, "reply_markup": {}}
        async with httpx.AsyncClient() as client:
            await client.post(url, json=payload, timeout=10)

        # 状態を別メッセージで通知
        url2 = f"{_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        async with httpx.AsyncClient() as client:
            await client.post(
                url2,
                json={
                    "chat_id": chat_id,
                    "reply_to_message_id": message_id,
                    "text": status_line,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
    except Exception:
        logger.exception("edit_card_status failed")
