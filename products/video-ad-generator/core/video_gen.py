"""後方互換のための thin wrapper。
新規コードは core.video_providers から get_provider("seedance") を使うこと。
"""

from __future__ import annotations
import logging
from pathlib import Path
from core.video_providers import VideoGenRequest, get_provider

logger = logging.getLogger(__name__)


class VideoGenError(Exception):
    """後方互換のためのエイリアス。新規コードは get_provider("seedance") を直接呼び、
    core.video_providers.seedance.SeedanceError を扱うこと。"""

    pass


async def generate_video(
    image_path: Path, video_prompt: str, output_path: Path
) -> Path:
    """既存呼び出しとの後方互換。Seedance 9:16/10s 固定で動画生成。"""
    provider = get_provider("seedance")
    req = VideoGenRequest(
        image_path=image_path,
        video_prompt=video_prompt,
        aspect_ratio="9:16",
        duration_seconds=10,
        camera_preset=None,
        output_path=output_path,
    )
    try:
        return await provider.generate(req)
    except Exception as e:
        raise VideoGenError(str(e)) from e
