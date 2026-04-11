"""NanoBanana PRO API クライアント。
9:16（1080×1920）の日本人女性画像を生成する。
"""
from __future__ import annotations
import asyncio
import logging
from pathlib import Path
import httpx
from config import NANOBANANA_API_KEY, NANOBANANA_API_URL

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 5.0


class ImageGenError(Exception):
    pass


async def generate_image(prompt: str, output_path: Path) -> Path:
    """NanoBanana PRO で画像を生成して output_path に保存する。
    失敗時は最大3回リトライ。
    """
    headers = {
        "Authorization": f"Bearer {NANOBANANA_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": prompt,
        "aspect_ratio": "9:16",
        "width": 1080,
        "height": 1920,
        "model": "nanobanana-pro",
    }

    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await client.post(NANOBANANA_API_URL, headers=headers, json=payload)
                if response.status_code == 200:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(response.content)
                    logger.info(f"画像生成成功: {output_path}")
                    return output_path
                last_error = ImageGenError(f"HTTP {response.status_code}: {response.text[:200]}")
                logger.warning(f"Attempt {attempt} failed: {last_error}")
            except httpx.RequestError as e:
                last_error = ImageGenError(f"Request error: {e}")
                logger.warning(f"Attempt {attempt} request error: {e}")

            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)

    raise ImageGenError(f"画像生成失敗（{MAX_RETRIES}回リトライ済み）: {last_error}")
