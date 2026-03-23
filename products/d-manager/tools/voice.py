"""Voice memo — download Telegram voice, transcribe with OpenAI Whisper API."""

import logging
import os
import tempfile
from typing import Optional

import httpx
from telegram import Bot

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


async def transcribe_audio(audio_content: bytes) -> str:
    """Transcribe audio bytes using OpenAI Whisper API.

    Args:
        audio_content: Raw audio bytes

    Returns:
        Transcribed text, or error message
    """
    if not OPENAI_API_KEY:
        return "[音声メモ] OpenAI APIキーが設定されていないため、文字起こしできません。"

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(audio_content)
            temp_path = f.name

        async with httpx.AsyncClient() as client:
            with open(temp_path, "rb") as audio_file:
                resp = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    files={"file": ("audio.ogg", audio_file, "audio/ogg")},
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
        if temp_path:
            try:
                os.unlink(temp_path)
            except Exception:
                pass


async def download_telegram_voice(bot: Bot, file_id: str) -> Optional[bytes]:
    """Download voice/audio content from Telegram."""
    try:
        tg_file = await bot.get_file(file_id)
        audio_bytes = await tg_file.download_as_bytearray()
        return bytes(audio_bytes)
    except Exception as e:
        logger.error(f"Telegram voice download error: {e}")
        return None
