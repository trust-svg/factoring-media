import pytest
from pathlib import Path
from core.video_providers import (
    VideoProvider,
    VideoGenRequest,
    PROGRESS_STAGES,
    get_provider,
)
from core.video_providers.seedance import SeedanceProvider


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


def test_video_gen_request_quality_default():
    req = VideoGenRequest(
        image_path=Path("/tmp/x.jpg"),
        video_prompt="t",
        aspect_ratio="9:16",
        duration_seconds=10,
        camera_preset=None,
        output_path=Path("/tmp/o.mp4"),
    )
    assert req.quality == "low"


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


def test_get_provider_seedance():
    p = get_provider("seedance")
    assert p.name == "seedance"


def test_get_provider_veo3_lite():
    p = get_provider("veo3_lite")
    assert p.name == "veo3_lite"


def test_get_provider_kling3_pro():
    p = get_provider("kling3_pro")
    assert p.name == "kling3_pro"


def test_validate_rejects_unsupported_quality():
    p = _DummyProvider()
    req = _make_req()
    req.quality = "ultra"
    with pytest.raises(ValueError, match="quality"):
        p.validate(req)


def test_dummy_provider_supports_default_qualities():
    p = _DummyProvider()
    assert p.supported_qualities == ("low", "high")


def test_calc_cost_per_second_basis():
    class _RateP(VideoProvider):
        name = "rateP_sec"
        supported_aspects = ("9:16",)
        supported_durations = (10,)
        cost_basis = "per_second"
        RATE_MAP = {"low": 0.1, "high": 0.2}

        async def generate(self, req):
            return req.output_path

    req = _make_req()
    assert _RateP().calc_cost(req) == round(0.1 * 10, 4)
    req.quality = "high"
    assert _RateP().calc_cost(req) == round(0.2 * 10, 4)


def test_calc_cost_per_video_basis():
    class _RateV(VideoProvider):
        name = "rateP_vid"
        supported_aspects = ("9:16",)
        supported_durations = (10,)
        cost_basis = "per_video"
        RATE_MAP = {"low": 0.5, "high": 1.0}

        async def generate(self, req):
            return req.output_path

    req = _make_req()
    assert _RateV().calc_cost(req) == 0.5
    req.quality = "high"
    assert _RateV().calc_cost(req) == 1.0


def test_seedance_supports_new_aspects():
    p = SeedanceProvider()
    for aspect in ("9:16", "16:9", "1:1", "4:3", "3:4", "21:9"):
        req = _make_req(aspect=aspect)
        p.validate(req)


def test_seedance_cost_basis_is_per_video():
    p = SeedanceProvider()
    assert p.cost_basis == "per_video"


def test_seedance_calc_cost_low_vs_high():
    p = SeedanceProvider()
    low = _make_req()
    low.quality = "low"
    high = _make_req()
    high.quality = "high"
    assert p.calc_cost(low) < p.calc_cost(high)


def test_seedance_low_cost_per_video():
    p = SeedanceProvider()
    req = _make_req(duration=10)
    req.quality = "low"
    assert p.calc_cost(req) == 0.06


def test_seedance_high_cost_per_video():
    p = SeedanceProvider()
    req = _make_req(duration=10)
    req.quality = "high"
    assert p.calc_cost(req) == 0.18
