"""Discord webhook sender."""

import os
import requests


def send_discord(text: str) -> None:
    webhook_url = os.environ["DISCORD_WEBHOOK_URL"]
    # Discord message limit is 2000 chars per message
    for i in range(0, len(text), 2000):
        chunk = text[i : i + 2000]
        resp = requests.post(webhook_url, json={"content": chunk}, timeout=10)
        resp.raise_for_status()
