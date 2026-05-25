"""画像処理ユーティリティ — 白背景化（PhotoRoom API）。

deal-watcher/image_utils.py から移植。PHOTOROOM_API_KEY は .env に設定。
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
from urllib.parse import urlparse

import requests
from PIL import Image

logger = logging.getLogger(__name__)

MAX_IMAGE_PX = 2000
MIN_IMAGE_PX = 800  # eBay 最低 500px の規約に余裕を持たせる


def _whitebg_sync(image_url: str) -> bytes:
    """同期版: 仕入元URL → 白背景JPEG bytes。"""
    api_key = os.getenv("PHOTOROOM_API_KEY")
    if not api_key:
        raise ValueError("PHOTOROOM_API_KEY が .env に設定されていません")

    parsed = urlparse(image_url)
    referer_origin = f"{parsed.scheme}://{parsed.netloc}/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": referer_origin,
    }
    dl_resp = requests.get(image_url, headers=headers, timeout=30)
    dl_resp.raise_for_status()

    pr_resp = requests.post(
        "https://sdk.photoroom.com/v1/segment",
        headers={"x-api-key": api_key, "Accept": "image/png"},
        files={"image_file": ("image.jpg", dl_resp.content, "image/jpeg")},
        timeout=120,
    )
    pr_resp.raise_for_status()

    rgba = Image.open(io.BytesIO(pr_resp.content)).convert("RGBA")

    # 上限超過なら縮小
    if max(rgba.size) > MAX_IMAGE_PX:
        rgba.thumbnail((MAX_IMAGE_PX, MAX_IMAGE_PX), Image.LANCZOS)

    # eBay 最低解像度 500px を満たさない場合は LANCZOS で upscale
    longest = max(rgba.size)
    if longest < MIN_IMAGE_PX:
        scale = MIN_IMAGE_PX / longest
        new_w = max(1, int(round(rgba.width * scale)))
        new_h = max(1, int(round(rgba.height * scale)))
        rgba = rgba.resize((new_w, new_h), Image.LANCZOS)
        logger.info(f"upscale: {longest}px → {max(rgba.size)}px (eBay 500px 規約)")

    side = max(rgba.size)
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    px = (side - rgba.width) // 2
    py = (side - rgba.height) // 2
    canvas.paste(rgba, (px, py), mask=rgba.split()[3])

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=95, optimize=True)
    return buf.getvalue()


async def whitebg_from_url(image_url: str) -> bytes:
    """非同期: _whitebg_sync をスレッドプールで実行。"""
    return await asyncio.to_thread(_whitebg_sync, image_url)


async def whitebg_many(
    image_urls: list[str],
) -> list[tuple[str, bytes | None, str | None]]:
    """複数URLを並列処理。結果は (url, jpeg_bytes or None, error or None) のリスト。"""

    async def _one(url: str) -> tuple[str, bytes | None, str | None]:
        try:
            data = await whitebg_from_url(url)
            return (url, data, None)
        except Exception as e:
            logger.warning(f"white-bg failed for {url}: {e}")
            return (url, None, str(e))

    return await asyncio.gather(*[_one(u) for u in image_urls])
