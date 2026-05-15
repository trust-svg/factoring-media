import base64
import json
from unittest.mock import MagicMock, patch


def _make_claude_response(score: float, feedback: str) -> MagicMock:
    payload = {
        "score": score,
        "feedback": feedback,
        "criteria": {
            "content": {"score": 3, "max": 4, "comment": "内容は適切です"},
            "grammar": {"score": 2, "max": 3, "comment": "文法は概ね正確です"},
            "vocabulary": {"score": 2, "max": 3, "comment": "語彙は適切です"},
        },
    }
    msg = MagicMock()
    msg.content = [MagicMock()]
    msg.content[0].text = json.dumps(payload)
    return msg


def test_score_writing_passing():
    mock_resp = _make_claude_response(7.0, "よく書けています。")
    with patch("app.services.ai_service.anthropic_client") as mock_client:
        mock_client.messages.create.return_value = mock_resp
        from app.services import ai_service

        result = ai_service.score_writing(
            "Write about pets.", "I think pets are great."
        )
    assert result.score == 7.0
    assert result.max_score == 10.0
    assert result.is_passing is True
    assert "content" in result.criteria


def test_score_writing_failing():
    mock_resp = _make_claude_response(4.0, "もう少し頑張りましょう。")
    with patch("app.services.ai_service.anthropic_client") as mock_client:
        mock_client.messages.create.return_value = mock_resp
        from app.services import ai_service

        result = ai_service.score_writing("Write about pets.", "ok")
    assert result.score == 4.0
    assert result.is_passing is False


def test_generate_audio_returns_base64():
    fake_bytes = b"fake-mp3-data"
    mock_resp = MagicMock()
    mock_resp.content = fake_bytes
    with patch("app.services.ai_service.openai_client") as mock_client:
        mock_client.audio.speech.create.return_value = mock_resp
        from app.services import ai_service

        result = ai_service.generate_audio("Hello world")
    assert result.audio_base64 == base64.b64encode(fake_bytes).decode()


def test_transcribe_audio():
    mock_resp = MagicMock()
    mock_resp.text = "I think smartphones are useful for students."
    with patch("app.services.ai_service.openai_client") as mock_client:
        mock_client.audio.transcriptions.create.return_value = mock_resp
        from app.services import ai_service

        result = ai_service.transcribe_audio(b"fake-audio-bytes", "recording.webm")
    assert "smartphones" in result


def test_score_speaking_includes_transcript():
    mock_claude = _make_claude_response(6.0, "まあまあです。")
    mock_whisper = MagicMock()
    mock_whisper.text = "I think it is good."
    with (
        patch("app.services.ai_service.anthropic_client") as mock_ant,
        patch("app.services.ai_service.openai_client") as mock_oai,
    ):
        mock_ant.messages.create.return_value = mock_claude
        mock_oai.audio.transcriptions.create.return_value = mock_whisper
        from app.services import ai_service

        result = ai_service.score_speaking(
            "smartphones", ["learning", "distraction"], b"fake"
        )
    assert result.transcript == "I think it is good."
    assert result.score == 6.0
