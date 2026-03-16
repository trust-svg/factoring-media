"""Voice memo — download LINE audio, transcribe with OpenAI Whisper API."""

import logging
import os
import tempfile
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


async def transcribe_audio(audio_content: bytes) -> str:
    """Transcribe audio bytes using OpenAI Whisper API.

    Args:
        audio_content: Raw audio bytes from LINE message

    Returns:
        Transcribed text, or error message
    """
    if not OPENAI_API_KEY:
        return "[音声メモ] OpenAI APIキーが設定されていないため、文字起こしできません。"

    try:
        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as f:
            f.write(audio_content)
            temp_path = f.name

        async with httpx.AsyncClient() as client:
            with open(temp_path, "rb") as audio_file:
                resp = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    files={"file": ("audio.m4a", audio_file, "audio/mp4")},
                    data={"model": "whisper-1", "language": "ja"},
                    timeout=30,
                )

            if resp.status_code == 200:
                text = resp.json().get("text", "")
                return text if text else "[音声メモ] 音声を認識できませんでした。"
            else:
                logger.error(f"Whisper API error: {resp.status_code} {resp.text}")
                return f"[音声メモ] 文字起こしに失敗しました (HTTP {resp.status_code})"

    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return f"[音声メモ] エラー: {e}"
    finally:
        try:
            os.unlink(temp_path)
        except Exception:
            pass


async def download_line_audio(message_id: str, channel_token: str) -> Optional[bytes]:
    """Download audio content from LINE message."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api-data.line.me/v2/bot/message/{message_id}/content",
                headers={"Authorization": f"Bearer {channel_token}"},
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.content
            logger.error(f"LINE content download error: {resp.status_code}")
            return None
    except Exception as e:
        logger.error(f"LINE content download error: {e}")
        return None
