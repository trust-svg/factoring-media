"""Notification module — LINE and Telegram support.

If TELEGRAM_BOT_TOKEN is set, Telegram is used (free, unlimited).
Otherwise falls back to LINE Messaging API.
"""
import httpx
import config
import logging

logger = logging.getLogger(__name__)

PLATFORM_LABELS = {
    "yahoo_auction": "ヤフオク",
    "mercari": "メルカリ",
    "yahoo_fleamarket": "Yahooフリマ",
    "rakuma": "ラクマ",
    "hardoff": "ハードオフ",
    "yahoo_shopping": "Yahooショッピング",
    "rakuten": "楽天",
}


# ── Telegram ─────────────────────────────────────────────

async def _send_telegram(text: str, reply_markup: dict = None):
    """Send message via Telegram Bot API."""
    token = getattr(config, "TELEGRAM_BOT_TOKEN", "")
    chat_id = getattr(config, "TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        import json
        payload["reply_markup"] = json.dumps(reply_markup)

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json=payload,
                timeout=10,
            )
            if resp.status_code != 200:
                logger.error(f"Telegram API error: {resp.status_code} {resp.text}")
                return False
            return True
        except Exception as e:
            logger.error(f"Telegram notification failed: {e}")
            return False


def _use_telegram() -> bool:
    """Check if Telegram is configured."""
    return bool(getattr(config, "TELEGRAM_BOT_TOKEN", "")) and bool(getattr(config, "TELEGRAM_CHAT_ID", ""))


# ── LINE ─────────────────────────────────────────────────

async def _broadcast(messages: list):
    """Send messages via LINE broadcast API."""
    if not config.LINE_CHANNEL_TOKEN:
        logger.warning("LINE_CHANNEL_TOKEN not set, skipping LINE notification")
        return
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                "https://api.line.me/v2/bot/message/broadcast",
                headers={
                    "Authorization": f"Bearer {config.LINE_CHANNEL_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={"messages": messages},
                timeout=10,
            )
            if resp.status_code != 200:
                logger.error(f"LINE API error: {resp.status_code} {resp.text}")
        except Exception as e:
            logger.error(f"LINE notification failed: {e}")


# ── Public API (auto-selects Telegram or LINE) ───────────

async def notify_line(platform: str, title: str, price, url: str):
    """Send new listing notification."""
    label = PLATFORM_LABELS.get(platform, platform)
    price_str = f"¥{price:,}" if price else "価格不明"

    if _use_telegram():
        text = f"🔔 <b>新着発見！</b>\n【{label}】\n{title}\n💰 {price_str}\n🔗 {url}"
        await _send_telegram(text)
    else:
        message = {
            "type": "text",
            "text": f"🔔 新着発見！\n【{label}】\n{title}\n💰 {price_str}\n🔗 {url}",
        }
        await _broadcast([message])


async def notify_line_message(msg: str):
    """Send a raw text message."""
    if _use_telegram():
        await _send_telegram(msg)
    else:
        await _broadcast([{"type": "text", "text": msg}])


async def notify_line_flex(alt_text: str, contents: dict, buttons: list = None):
    """Send a rich notification with buttons.

    For Telegram: converts to text + inline keyboard buttons.
    For LINE: sends as Flex Message.

    Args:
        alt_text: Summary text
        contents: LINE Flex Message contents (dict)
        buttons: Optional list of {"label": str, "url": str} for Telegram buttons.
                 If not provided, extracted from Flex Message footer.
    """
    if _use_telegram():
        # Extract text from Flex body
        text = f"<b>{alt_text}</b>"

        body = contents.get("body", {})
        for item in body.get("contents", []):
            if item.get("type") == "text":
                t = item.get("text", "")
                weight = item.get("weight", "")
                color = item.get("color", "")
                if weight == "bold" and color:
                    text += f"\n\n<b>{t}</b>"
                elif weight == "bold":
                    text += f"\n<b>{t}</b>"
                else:
                    text += f"\n{t}"
            elif item.get("type") == "box" and item.get("layout") == "horizontal":
                parts = item.get("contents", [])
                if len(parts) == 2:
                    label = parts[0].get("text", "")
                    value = parts[1].get("text", "")
                    text += f"\n{label}: {value}"
            elif item.get("type") == "separator":
                text += "\n───────────"

        # Extract buttons from footer or provided list
        if not buttons:
            buttons = []
            footer = contents.get("footer", {})
            for item in _flatten_buttons(footer):
                action = item.get("action", {})
                if action.get("type") == "uri":
                    buttons.append({
                        "label": action.get("label", ""),
                        "url": action.get("uri", ""),
                    })

        # Build Telegram inline keyboard
        reply_markup = None
        if buttons:
            keyboard = []
            for btn in buttons:
                if btn.get("url"):
                    keyboard.append([{
                        "text": btn["label"],
                        "url": btn["url"],
                    }])
            if keyboard:
                reply_markup = {"inline_keyboard": keyboard}

        await _send_telegram(text, reply_markup=reply_markup)
    else:
        # LINE Flex Message
        message = {
            "type": "flex",
            "altText": alt_text,
            "contents": contents,
        }
        await _broadcast([message])


def _flatten_buttons(container: dict) -> list:
    """Recursively extract button elements from a LINE Flex container."""
    results = []
    if not container:
        return results
    if container.get("type") == "button":
        results.append(container)
    for item in container.get("contents", []):
        if item.get("type") == "button":
            results.append(item)
        elif item.get("type") == "box":
            results.extend(_flatten_buttons(item))
    return results
