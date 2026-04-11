import pytest
import httpx
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from core.video_gen import generate_video, VideoGenError

FAKE_VIDEO_BYTES = b"RIFF" + b"\x00" * 200  # fake video bytes

async def test_generate_video_success(tmp_path, monkeypatch):
    image_path = tmp_path / "test.jpg"
    image_path.write_bytes(b"fake_image_data")
    output_path = tmp_path / "test.mp4"

    # Mock the client to simulate the three-step process
    # Step1: POST to submit job returns request_id
    submit_response = MagicMock()
    submit_response.status_code = 200
    submit_response.json.return_value = {"request_id": "req_abc123"}

    # Step2: GET to poll status returns done with video URL
    status_response = MagicMock()
    status_response.status_code = 200
    status_response.json.return_value = {"status": "done", "output_url": "https://cdn.example.com/video.mp4"}

    # Step3: GET to download video returns bytes
    download_response = MagicMock()
    download_response.status_code = 200
    download_response.content = FAKE_VIDEO_BYTES
    download_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=submit_response)
    mock_client.get = AsyncMock(side_effect=[status_response, download_response])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr("core.video_gen.httpx.AsyncClient", lambda **kwargs: mock_client)
    # Speed up polling for tests
    monkeypatch.setattr("core.video_gen.POLL_INTERVAL", 0.01)

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

    # Mock client that returns 500 error
    error_response = MagicMock()
    error_response.status_code = 500
    error_response.text = "server error"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=error_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr("core.video_gen.httpx.AsyncClient", lambda **kwargs: mock_client)

    with pytest.raises(VideoGenError):
        await generate_video(image_path=image_path, video_prompt="test", output_path=output_path)
