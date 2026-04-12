"""NanoBanana PRO API クライアント。
Google Gemini 3 Pro Image (gemini-3-pro-image-preview) を使用して
9:16（1080×1920）の日本人女性画像を生成する。
"""
from __future__ import annotations
import asyncio
import logging
from pathlib import Path
try:
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover — テスト環境では monkeypatch で置換
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]
from config import GEMINI_API_KEY, NANOBANANA_MODEL

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 5.0


class ImageGenError(Exception):
    pass


async def generate_image(prompt: str, output_path: Path) -> Path:
    """NanoBanana PRO で画像を生成して output_path に保存する。
    失敗時は最大3回リトライ。
    """
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = await client.aio.models.generate_content(
                model=NANOBANANA_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                    image_config=types.ImageConfig(
                        aspect_ratio="9:16",
                        image_size="2K",
                    ),
                ),
            )
            for part in response.parts:
                if part.inline_data is not None:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    image = part.as_image()
                    image.save(str(output_path))
                    logger.info(f"画像生成成功: {output_path}")
                    return output_path
            last_error = ImageGenError("レスポンスに画像が含まれていませんでした")
            logger.warning(f"Attempt {attempt}: レスポンスに画像なし")
        except ImageGenError:
            raise
        except Exception as e:
            last_error = ImageGenError(f"API error: {e}")
            logger.warning(f"Attempt {attempt} failed: {e}")

        if attempt < MAX_RETRIES:
            await asyncio.sleep(RETRY_DELAY)

    raise ImageGenError(f"画像生成失敗（{MAX_RETRIES}回リトライ済み）: {last_error}")
