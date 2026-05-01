import pytest
from pathlib import Path
from core.video_providers import (
    VideoProvider,
    VideoGenRequest,
    PROGRESS_STAGES,
    get_provider,
)


class _DummyProvider(VideoProvider):
    name = "dummy"
    supported_aspects = ("9:16",)
    supported_durations = (10,)

    async def generate(self, req: VideoGenRequest) -> Path:
        return req.output_path

    def calc_cost(self, req: VideoGenRequest) -> float:
        return 0.5


def _make_req(aspect="9:16", duration=10):
    return VideoGenRequest(
        image_path=Path("/tmp/x.jpg"),
        video_prompt="test",
        aspect_ratio=aspect,
        duration_seconds=duration,
        camera_preset=None,
        output_path=Path("/tmp/out.mp4"),
    )


def test_validate_passes_for_supported():
    p = _DummyProvider()
    p.validate(_make_req())  # no exception


def test_validate_rejects_unsupported_aspect():
    p = _DummyProvider()
    with pytest.raises(ValueError, match="aspect"):
        p.validate(_make_req(aspect="1:1"))


def test_validate_rejects_unsupported_duration():
    p = _DummyProvider()
    with pytest.raises(ValueError, match="duration"):
        p.validate(_make_req(duration=5))


def test_progress_stages_defined():
    assert "uploading_image" in PROGRESS_STAGES
    assert "submitting" in PROGRESS_STAGES
    assert "polling" in PROGRESS_STAGES
    assert "downloading_video" in PROGRESS_STAGES


def test_get_provider_unknown_raises():
    with pytest.raises(ValueError, match="unknown provider"):
        get_provider("nonexistent_provider")
