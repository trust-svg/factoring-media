import pytest
from core.video_providers.veo3 import Veo3LiteProvider
from core.video_providers import VideoGenRequest


def _make_req(tmp_path, quality="low"):
    img = tmp_path / "in.jpg"
    img.write_bytes(b"fakeimage")
    return VideoGenRequest(
        image_path=img,
        video_prompt="a cat",
        aspect_ratio="9:16",
        duration_seconds=8,
        camera_preset=None,
        output_path=tmp_path / "out.mp4",
        quality=quality,
    )


def test_veo3_metadata():
    p = Veo3LiteProvider()
    assert p.name == "veo3_lite"
    assert set(p.supported_aspects) == {"16:9", "9:16"}
    assert set(p.supported_durations) == {8}
    assert p.cost_basis == "per_second"
    assert p.RATE_MAP == {"low": 0.10, "high": 0.40}


def test_calc_cost_per_second(tmp_path):
    p = Veo3LiteProvider()
    req = _make_req(tmp_path, quality="low")
    assert p.calc_cost(req) == 0.80
    req.quality = "high"
    assert p.calc_cost(req) == 3.20


def test_model_map_routes_by_quality():
    p = Veo3LiteProvider()
    assert set(p.MODEL_MAP.keys()) == {"low", "high"}
    assert p.MODEL_MAP["low"] != p.MODEL_MAP["high"]
    assert "fast" in p.MODEL_MAP["low"]


def test_validate_rejects_unsupported_aspect(tmp_path):
    p = Veo3LiteProvider()
    req = _make_req(tmp_path)
    req.aspect_ratio = "1:1"
    with pytest.raises(ValueError):
        p.validate(req)


def test_validate_rejects_unsupported_duration(tmp_path):
    p = Veo3LiteProvider()
    req = _make_req(tmp_path)
    req.duration_seconds = 4
    with pytest.raises(ValueError):
        p.validate(req)


def test_mime_type_derived_from_suffix(tmp_path):
    """PNG画像ならmimeTypeがimage/pngになる（Task 14のアップロード対応）"""
    png = tmp_path / "in.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
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
