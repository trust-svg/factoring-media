"""Telegram Bot 経由で画像をアップロードして公開URLを取得する共通関数。
全プロバイダーが同じ方式で画像URLを準備するために使う。
"""

from __future__ import annotations
import logging
from pathlib import Path
import httpx
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


async def upload_image_to_telegram(image_path: Path) -> str:
    """画像を Telegram にアップロードして公開ダウンロードURLを返す。"""
    base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        with open(image_path, "rb") as f:
            resp = await client.post(
                f"{base_url}/sendDocument",
                data={"chat_id": TELEGRAM_CHAT_ID},
                files={"document": (image_path.name, f, "image/jpeg")},
            )
        resp.raise_for_status()
        result = resp.json()
        file_id = result["result"]["document"]["file_id"]

        resp2 = await client.get(f"{base_url}/getFile", params={"file_id": file_id})
        resp2.raise_for_status()
        file_path = resp2.json()["result"]["file_path"]

        download_url = (
            f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
        )
        logger.info(f"Telegram upload OK: {download_url}")
        return download_url
