"""白背景化ユーティリティ（非同期版 / Python 3.9対応）。

asyncio.to_thread で同期処理をスレッドプールに委譲。
"""

import asyncio
import io
import logging
import os
from typing import Optional
from urllib.parse import urlparse

import requests
from PIL import Image

logger = logging.getLogger(__name__)

MAX_IMAGE_PX = 2000


def _whitebg_sync(image_url):
    # type: (str) -> bytes
    """同期版: 仕入元URL → 白背景JPEG bytes。スレッドプール内で実行される。"""
    api_key = os.getenv("PHOTOROOM_API_KEY")
    if not api_key:
        raise ValueError("PHOTOROOM_API_KEY が .env に設定されていません")

    parsed = urlparse(image_url)
    referer_origin = "{0}://{1}/".format(parsed.scheme, parsed.netloc)
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
    if max(rgba.size) > MAX_IMAGE_PX:
        rgba.thumbnail((MAX_IMAGE_PX, MAX_IMAGE_PX), Image.LANCZOS)

    side = max(rgba.size)
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    px = (side - rgba.width) // 2
    py = (side - rgba.height) // 2
    canvas.paste(rgba, (px, py), mask=rgba.split()[3])

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=95, optimize=True)
    return buf.getvalue()


async def whitebg_from_url(image_url):
    # type: (str) -> bytes
    """非同期ラッパー: _whitebg_sync をスレッドプールで実行。"""
    return await asyncio.to_thread(_whitebg_sync, image_url)
