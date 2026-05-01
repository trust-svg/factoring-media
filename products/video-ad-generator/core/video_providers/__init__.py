"""動画生成プロバイダー抽象基底クラス。"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

__all__ = ["VideoProvider", "VideoGenRequest", "PROGRESS_STAGES", "get_provider"]

PROGRESS_STAGES: tuple[str, ...] = (
    "uploading_image",
    "submitting",
    "polling",
    "downloading_video",
)


@dataclass(frozen=True)
class VideoGenRequest:
    image_path: Path
    video_prompt: str
    aspect_ratio: str
    duration_seconds: int
    camera_preset: str | None
    output_path: Path


class VideoProvider(ABC):
    """全プロバイダーが継承する基底クラス。"""

    name: str = ""
    supported_aspects: tuple[str, ...] = ()
    supported_durations: tuple[int, ...] = ()

    @abstractmethod
    async def generate(self, req: VideoGenRequest) -> Path:
        """画像と prompt から動画を生成し、output_path に保存して返す。"""

    @abstractmethod
    def calc_cost(self, req: VideoGenRequest) -> float:
        """ジョブのコストを USD で返す。"""

    def validate(self, req: VideoGenRequest) -> None:
        if req.aspect_ratio not in self.supported_aspects:
            raise ValueError(
                f"{self.name} does not support aspect {req.aspect_ratio}. "
                f"Supported: {self.supported_aspects}"
            )
        if req.duration_seconds not in self.supported_durations:
            raise ValueError(
                f"{self.name} does not support duration {req.duration_seconds}s. "
                f"Supported: {self.supported_durations}"
            )


def get_provider(name: str) -> VideoProvider:
    """プロバイダー名から実装インスタンスを返すファクトリ。"""
    if name == "seedance":
        from core.video_providers.seedance import SeedanceProvider

        return SeedanceProvider()
    if name == "veo3_lite":
        from core.video_providers.veo3 import Veo3LiteProvider

        return Veo3LiteProvider()
    if name == "kling3_pro":
        from core.video_providers.kling import Kling3ProProvider

        return Kling3ProProvider()
    raise ValueError(f"unknown provider: {name}")
