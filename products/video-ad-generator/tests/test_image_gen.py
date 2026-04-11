import pytest
import httpx
import respx
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from core.image_gen import generate_image, ImageGenError

FAKE_IMAGE_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # fake PNG bytes


@pytest.mark.asyncio
async def test_generate_image_success(tmp_path, monkeypatch):
    output_path = tmp_path / "test.jpg"

    # Mock httpx.AsyncClient
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = FAKE_IMAGE_BYTES

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr("core.image_gen.httpx.AsyncClient", lambda **kwargs: mock_client)

    result = await generate_image(
        prompt="A Japanese woman in her 40s at a cafe",
        output_path=output_path,
    )
    assert result == output_path
    assert output_path.exists()


@pytest.mark.asyncio
async def test_generate_image_retries_on_error(tmp_path, monkeypatch):
    output_path = tmp_path / "test.jpg"

    # Mock httpx.AsyncClient with side_effect for retries
    mock_error_response = MagicMock()
    mock_error_response.status_code = 500
    mock_error_response.text = "server error"

    mock_success_response = MagicMock()
    mock_success_response.status_code = 200
    mock_success_response.content = FAKE_IMAGE_BYTES

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        side_effect=[mock_error_response, mock_error_response, mock_success_response]
    )
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr("core.image_gen.httpx.AsyncClient", lambda **kwargs: mock_client)
    monkeypatch.setattr("core.image_gen.RETRY_DELAY", 0.1)  # Speed up test

    result = await generate_image(prompt="test", output_path=output_path)
    assert result == output_path


@pytest.mark.asyncio
async def test_generate_image_raises_after_max_retries(tmp_path, monkeypatch):
    output_path = tmp_path / "test.jpg"

    # Mock httpx.AsyncClient to always fail
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "server error"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr("core.image_gen.httpx.AsyncClient", lambda **kwargs: mock_client)
    monkeypatch.setattr("core.image_gen.RETRY_DELAY", 0.1)  # Speed up test

    with pytest.raises(ImageGenError):
        await generate_image(prompt="test", output_path=output_path)
