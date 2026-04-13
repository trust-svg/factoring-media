# tests/test_profile_bot.py
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from bots.profile_bot import diagnose_photo, format_diagnosis_result


def test_format_diagnosis_result():
    result = format_diagnosis_result(
        score=6.8,
        points=["背景に生活感が出ている（-1.2点）", "表情が硬い（-0.9点）", "逆光で顔が暗い（-0.6点）"],
        potential_score=8.5,
        is_free=True,
    )
    assert "6.8" in result
    assert "8.5" in result
    assert "背景に生活感" in result
    assert "Standard" in result  # アップセルCTAが含まれる


def test_format_diagnosis_result_standard():
    result = format_diagnosis_result(
        score=7.5,
        points=["笑顔を増やすと印象UP", "背景をシンプルに", "明るさを調整"],
        potential_score=9.0,
        is_free=False,
    )
    assert "Standard" not in result  # 有料ユーザーにはCTAなし
    assert "9.0" in result


@pytest.mark.asyncio
async def test_diagnose_photo_returns_score_and_points():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({
        "score": 6.8,
        "points": ["背景に生活感", "表情が硬い", "逆光"],
        "potential_score": 8.5
    }))]

    with patch("bots.profile_bot.anthropic.AsyncAnthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create = AsyncMock(return_value=mock_response)

        score, points, potential = await diagnose_photo(b"fake_image_bytes")

    assert score == 6.8
    assert len(points) == 3
    assert potential == 8.5
