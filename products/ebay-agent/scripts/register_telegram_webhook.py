"""Telegram setWebhook を 1 回だけ叩くスクリプト。

使い方:
    docker compose exec ebay-agent python scripts/register_telegram_webhook.py \
        https://ebay.trustlink-tk.com/webhook/telegram

URL を引数で渡せばそのまま setWebhook を呼ぶ。secret_token は
TELEGRAM_WEBHOOK_SECRET 環境変数があれば送る。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 親ディレクトリを sys.path に追加（docker exec 経由でも動くように）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/register_telegram_webhook.py <https-url>")
        return 1
    url = sys.argv[1]

    if not TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN is not set")
        return 2

    payload = {
        "url": url,
        "allowed_updates": ["callback_query", "message"],
        "drop_pending_updates": True,
    }
    if TELEGRAM_WEBHOOK_SECRET:
        payload["secret_token"] = TELEGRAM_WEBHOOK_SECRET

    api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
    resp = httpx.post(api, json=payload, timeout=20)
    print(f"HTTP {resp.status_code}")
    print(resp.text)
    return 0 if resp.status_code == 200 else 3


if __name__ == "__main__":
    sys.exit(main())
