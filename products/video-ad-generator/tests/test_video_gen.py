import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from core.video_gen import generate_video, VideoGenError

FAKE_VIDEO_BYTES = b"RIFF" + b"\x00" * 200  # fake video bytes


async def test_generate_video_success(tmp_path, monkeypatch):
    image_path = tmp_path / "test.jpg"
    image_path.write_bytes(b"fake_image_data")
    output_path = tmp_path / "test.mp4"

    # Fake provider whose .generate() writes the output file and returns output_path
    async def fake_generate(req):
        req.output_path.parent.mkdir(parents=True, exist_ok=True)
        req.output_path.write_bytes(FAKE_VIDEO_BYTES)
        return req.output_path

    fake_provider = MagicMock()
    fake_provider.generate = AsyncMock(side_effect=fake_generate)

    monkeypatch.setattr("core.video_gen.get_provider", lambda name: fake_provider)

    result = await generate_video(
        image_path=image_path,
        video_prompt="The woman smiles gently",
        output_path=output_path,
    )
    assert result == output_path
    assert output_path.exists()


async def test_generate_video_raises_on_api_error(tmp_path, monkeypatch):
    image_path = tmp_path / "test.jpg"
    image_path.write_bytes(b"fake_image_data")
    output_path = tmp_path / "test.mp4"

    # Fake provider whose .generate() raises an exception
    fake_provider = MagicMock()
    fake_provider.generate = AsyncMock(side_effect=RuntimeError("server error"))

    monkeypatch.setattr("core.video_gen.get_provider", lambda name: fake_provider)

    with pytest.raises(VideoGenError):
        await generate_video(
            image_path=image_path, video_prompt="test", output_path=output_path
        )
