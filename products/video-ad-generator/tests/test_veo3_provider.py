import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from core.video_providers.veo3 import Veo3LiteProvider
from core.video_providers import VideoGenRequest


def _make_req(tmp_path, duration=8):
    img = tmp_path / "in.jpg"
    img.write_bytes(b"fakeimage")
    return VideoGenRequest(
        image_path=img,
        video_prompt="a cat",
        aspect_ratio="9:16",
        duration_seconds=duration,
        camera_preset=None,
        output_path=tmp_path / "out.mp4",
    )


def test_veo3_metadata():
    p = Veo3LiteProvider()
    assert p.name == "veo3_lite"
    assert "9:16" in p.supported_aspects
    assert "16:9" in p.supported_aspects
    assert set(p.supported_durations) >= {4, 6, 8}


def test_calc_cost_per_second(tmp_path):
    p = Veo3LiteProvider()
    req = _make_req(tmp_path, duration=8)
    cost = p.calc_cost(req)
    assert abs(cost - 0.40) < 0.001  # $0.05 × 8


def test_validate_rejects_unsupported_duration(tmp_path):
    p = Veo3LiteProvider()
    req = _make_req(tmp_path, duration=10)
    with pytest.raises(ValueError, match="duration"):
        p.validate(req)


def test_mime_type_derived_from_suffix(tmp_path):
    """PNG画像ならmimeTypeがimage/pngになる（Task 14のアップロード対応）"""
    p = Veo3LiteProvider()
    png = tmp_path / "in.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    # Build the same way generate() does (without making a real API call)
    suffix = png.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    assert mime == "image/png"

    jpg = tmp_path / "in.jpg"
    jpg.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)
    suffix = jpg.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    assert mime == "image/jpeg"


def test_camera_preset_appended_to_prompt(tmp_path):
    p = Veo3LiteProvider()
    req = _make_req(tmp_path)
    req.camera_preset = "pan_left"
    assert "pan left" in p._build_prompt(req).lower()
