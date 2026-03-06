"""LINE通知モジュール — LINE Messaging API Push"""
from __future__ import annotations

import logging

import requests

from config import LINE_CHANNEL_TOKEN, LINE_USER_ID

logger = logging.getLogger(__name__)

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


def send_line_message(text: str) -> bool:
    """LINE Messaging API でプッシュメッセージを送信"""
    if not LINE_CHANNEL_TOKEN or not LINE_USER_ID:
        logger.warning("LINE credentials not configured — skipping notification")
        return False

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_TOKEN}",
    }
    payload = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": text}],
    }

    try:
        resp = requests.post(LINE_PUSH_URL, json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            logger.info("LINE notification sent")
            return True
        else:
            logger.error(f"LINE notification failed: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        logger.error(f"LINE notification error: {e}")
        return False
