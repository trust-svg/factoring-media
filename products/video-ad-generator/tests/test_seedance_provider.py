import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from core.video_providers.seedance import SeedanceProvider
from core.video_providers import VideoGenRequest


def _make_req(tmp_path):
    img = tmp_path / "in.jpg"
    img.write_bytes(b"fakeimage")
    return VideoGenRequest(
        image_path=img,
        video_prompt="a cat",
        aspect_ratio="9:16",
        duration_seconds=10,
        camera_preset=None,
        output_path=tmp_path / "out.mp4",
    )


def test_seedance_metadata():
    p = SeedanceProvider()
    assert p.name == "seedance"
    assert "9:16" in p.supported_aspects
    assert "16:9" in p.supported_aspects
    assert 5 in p.supported_durations
    assert 10 in p.supported_durations


def test_calc_cost_per_video(tmp_path):
    p = SeedanceProvider()
    req = _make_req(tmp_path)
    cost = p.calc_cost(req)
    assert cost > 0


def test_validate_rejects_1to1_ratio(tmp_path):
    p = SeedanceProvider()
    req = _make_req(tmp_path)
    req.aspect_ratio = "1:1"
    with pytest.raises(ValueError):
        p.validate(req)


def test_camera_preset_appended_to_prompt(tmp_path):
    """camera_preset が指定されたら prompt_hint がプロンプトに追加される"""
    p = SeedanceProvider()
    req = _make_req(tmp_path)
    req.camera_preset = "dolly_in"
    enriched = p._build_prompt(req)
    assert "dolly-in" in enriched


def test_no_camera_preset_keeps_prompt_clean(tmp_path):
    p = SeedanceProvider()
    req = _make_req(tmp_path)
    req.camera_preset = None
    assert p._build_prompt(req) == "a cat"
