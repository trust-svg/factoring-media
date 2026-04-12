import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock
import core.image_gen
from core.image_gen import generate_image, ImageGenError


def _make_fake_image(output_path: Path) -> MagicMock:
    """part.as_image() のモックを生成する。save() で実ファイルを書く。"""
    fake_image = MagicMock()
    fake_image.save = MagicMock(
        side_effect=lambda path: Path(path).write_bytes(b"\x89PNG\r\n" + b"\x00" * 50)
    )
    return fake_image


def _make_mock_part(has_image: bool = True) -> MagicMock:
    part = MagicMock()
    if has_image:
        part.inline_data = MagicMock()
        part.inline_data.mime_type = "image/png"
        part.as_image = MagicMock(return_value=_make_fake_image(None))
        part.text = None
    else:
        part.inline_data = None
        part.text = "some text"
    return part


def _patch_genai(monkeypatch, generate_content_coro):
    """core.image_gen.genai / types を差し替える。genai 未インストールでも動作する。"""
    mock_genai = MagicMock()
    mock_client_instance = MagicMock()
    mock_client_instance.aio.models.generate_content = generate_content_coro
    mock_genai.Client = MagicMock(return_value=mock_client_instance)
    monkeypatch.setattr(core.image_gen, "genai", mock_genai)
    monkeypatch.setattr(core.image_gen, "types", MagicMock())
    return mock_genai


@pytest.mark.asyncio
async def test_generate_image_success(tmp_path, monkeypatch):
    output_path = tmp_path / "test.png"
    mock_response = MagicMock()
    mock_response.parts = [_make_mock_part(has_image=True)]

    _patch_genai(monkeypatch, AsyncMock(return_value=mock_response))

    result = await generate_image(
        prompt="A Japanese woman in her 40s at a cafe",
        output_path=output_path,
    )
    assert result == output_path
    assert output_path.exists()


@pytest.mark.asyncio
async def test_generate_image_retries_on_error(tmp_path, monkeypatch):
    output_path = tmp_path / "test.png"
    mock_response = MagicMock()
    mock_response.parts = [_make_mock_part(has_image=True)]

    call_count = [0]

    async def flaky(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] < 3:
            raise Exception("temporary error")
        return mock_response

    _patch_genai(monkeypatch, flaky)
    monkeypatch.setattr(core.image_gen, "RETRY_DELAY", 0.01)

    result = await generate_image(prompt="test", output_path=output_path)
    assert result == output_path
    assert call_count[0] == 3


@pytest.mark.asyncio
async def test_generate_image_raises_after_max_retries(tmp_path, monkeypatch):
    output_path = tmp_path / "test.png"

    _patch_genai(monkeypatch, AsyncMock(side_effect=Exception("API error")))
    monkeypatch.setattr(core.image_gen, "RETRY_DELAY", 0.01)

    with pytest.raises(ImageGenError):
        await generate_image(prompt="test", output_path=output_path)
