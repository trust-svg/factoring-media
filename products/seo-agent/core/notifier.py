from __future__ import annotations

import os
import sys

import requests


def notify(message: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print(f"[notify-fallback] {message}", file=sys.stderr)
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        response = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        if response.status_code != 200:
            print(
                f"[notify-error] HTTP {response.status_code}: {response.text}",
                file=sys.stderr,
            )
    except Exception as e:
        print(f"[notify-error] {e}", file=sys.stderr)
