"""progress_callback がプロバイダー内で正しい順序で呼ばれることを検証。"""

from __future__ import annotations
import httpx
import pytest
from core.video_providers import VideoGenRequest
from core.video_providers.kling import Kling3ProProvider
from core.video_providers.seedance import SeedanceProvider
from core.video_providers.veo3 import Veo3LiteProvider


def _make_req(tmp_path, aspect="9:16", duration=10):
    img = tmp_path / "in.jpg"
    img.write_bytes(b"fakeimage")
    return VideoGenRequest(
        image_path=img,
        video_prompt="a cat",
        aspect_ratio=aspect,
        duration_seconds=duration,
        camera_preset=None,
        output_path=tmp_path / "out.mp4",
        quality="low",
    )


def _make_async_client_factory(handlers: dict):
    """httpx.AsyncClient をバイパスする MockTransport ベースのファクトリ。"""

    def _handler(request: httpx.Request) -> httpx.Response:
        return handlers[request.method](request)

    transport = httpx.MockTransport(_handler)

    class _FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs.pop("timeout", None)
            super().__init__(transport=transport, **kwargs)

    return _FakeAsyncClient


async def test_kling_calls_progress_in_order(tmp_path, monkeypatch):
    async def fake_upload(p):
        return "https://example.com/i.jpg"

    monkeypatch.setattr(
        "core.video_providers.kling.upload_image_to_telegram", fake_upload
    )
    monkeypatch.setattr("core.video_providers.kling.POLL_INTERVAL", 0.0)

    def post_handler(req):
        return httpx.Response(200, json={"request_id": "r1"})

    def get_handler(req):
        if "v.mp4" in str(req.url):
            return httpx.Response(200, content=b"fake_video")
        return httpx.Response(
            200,
            json={"status": "succeeded", "outputs": ["https://example.com/v.mp4"]},
        )

    fake = _make_async_client_factory({"POST": post_handler, "GET": get_handler})
    monkeypatch.setattr("core.video_providers.kling.httpx.AsyncClient", fake)

    captured: list[str] = []
    req = _make_req(tmp_path)
    await Kling3ProProvider().generate(
        req, progress_callback=lambda s: captured.append(s)
    )

    assert captured == ["uploading_image", "submitting", "polling", "downloading_video"]


async def test_seedance_calls_progress_in_order(tmp_path, monkeypatch):
    async def fake_upload(p):
        return "https://example.com/i.jpg"

    monkeypatch.setattr(
        "core.video_providers.seedance.upload_image_to_telegram", fake_upload
    )
    monkeypatch.setattr("core.video_providers.seedance.POLL_INTERVAL", 0.0)

    def post_handler(req):
        return httpx.Response(200, json={"request_id": "r2"})

    def get_handler(req):
        if "v.mp4" in str(req.url):
            return httpx.Response(200, content=b"fake_video")
        return httpx.Response(
            200,
            json={"status": "succeeded", "outputs": ["https://example.com/v.mp4"]},
        )

    fake = _make_async_client_factory({"POST": post_handler, "GET": get_handler})
    monkeypatch.setattr("core.video_providers.seedance.httpx.AsyncClient", fake)

    captured: list[str] = []
    req = _make_req(tmp_path)
    await SeedanceProvider().generate(
        req, progress_callback=lambda s: captured.append(s)
    )

    assert captured == ["uploading_image", "submitting", "polling", "downloading_video"]


async def test_veo3_calls_progress_in_order(tmp_path, monkeypatch):
    monkeypatch.setattr("core.video_providers.veo3.POLL_INTERVAL", 0.0)

    def post_handler(req):
        return httpx.Response(200, json={"name": "operations/op1"})

    def get_handler(req):
        if "v.mp4" in str(req.url):
            return httpx.Response(200, content=b"fake_video")
        return httpx.Response(
            200,
            json={
                "done": True,
                "response": {
                    "generatedVideos": [{"video": {"uri": "https://example.com/v.mp4"}}]
                },
            },
        )

    fake = _make_async_client_factory({"POST": post_handler, "GET": get_handler})
    monkeypatch.setattr("core.video_providers.veo3.httpx.AsyncClient", fake)

    captured: list[str] = []
    req = _make_req(tmp_path, aspect="9:16", duration=8)
    await Veo3LiteProvider().generate(
        req, progress_callback=lambda s: captured.append(s)
    )

    assert captured == ["submitting", "polling", "downloading_video"]


async def test_kling_progress_callback_optional(tmp_path, monkeypatch):
    """progress_callback=None でも例外なく動くことを確認（既存テスト互換）。"""

    async def fake_upload(p):
        return "https://example.com/i.jpg"

    monkeypatch.setattr(
        "core.video_providers.kling.upload_image_to_telegram", fake_upload
    )
    monkeypatch.setattr("core.video_providers.kling.POLL_INTERVAL", 0.0)

    def post_handler(req):
        return httpx.Response(200, json={"request_id": "r3"})

    def get_handler(req):
        if "v.mp4" in str(req.url):
            return httpx.Response(200, content=b"v")
        return httpx.Response(
            200,
            json={"status": "succeeded", "outputs": ["https://example.com/v.mp4"]},
        )

    fake = _make_async_client_factory({"POST": post_handler, "GET": get_handler})
    monkeypatch.setattr("core.video_providers.kling.httpx.AsyncClient", fake)

    req = _make_req(tmp_path)
    result = await Kling3ProProvider().generate(req)
    assert result.exists()
