import pytest
from pathlib import Path
from core.video_providers.kling import Kling3ProProvider
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


def test_kling_metadata():
    p = Kling3ProProvider()
    assert p.name == "kling3_pro"
    assert {"9:16", "16:9", "1:1"} <= set(p.supported_aspects)
    assert {3, 5, 10, 15} <= set(p.supported_durations)
    assert p.cost_basis == "per_video"
    assert p.RATE_MAP == {"low": 0.72, "high": 0.72}


def test_calc_cost_per_video(tmp_path):
    p = Kling3ProProvider()
    req = _make_req(tmp_path)
    req.quality = "low"
    assert p.calc_cost(req) == 0.72
    req.quality = "high"
    assert p.calc_cost(req) == 0.72


def test_url_map_routes_by_quality():
    p = Kling3ProProvider()
    assert set(p.URL_MAP.keys()) == {"low", "high"}
    assert p.URL_MAP["low"] != p.URL_MAP["high"]


def test_payload_uses_image_url_singular(tmp_path):
    p = Kling3ProProvider()
    req = _make_req(tmp_path)
    payload = p._build_payload(req, "https://example.com/img.jpg")
    assert payload["image_url"] == "https://example.com/img.jpg"
    assert "image" not in payload
    assert "aspect_ratio" not in payload


def test_camera_params_for_dolly_in(tmp_path):
    p = Kling3ProProvider()
    req = _make_req(tmp_path)
    req.camera_preset = "dolly_in"
    payload = p._build_payload(req, "https://example.com/img.jpg")
    assert "camera_control" in payload
    assert payload["camera_control"]["config"] == {"zoom": 5}


def test_no_camera_preset_omits_camera_control(tmp_path):
    p = Kling3ProProvider()
    req = _make_req(tmp_path)
    req.camera_preset = None
    payload = p._build_payload(req, "https://example.com/img.jpg")
    assert "camera_control" not in payload


def test_camera_preset_static_omits_camera_control(tmp_path):
    p = Kling3ProProvider()
    req = _make_req(tmp_path)
    req.camera_preset = "static"
    payload = p._build_payload(req, "https://example.com/img.jpg")
    assert "camera_control" not in payload
