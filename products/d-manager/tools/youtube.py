"""YouTube transcript tool — fetch transcripts and summarize content."""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


def _extract_video_id(url_or_id: str) -> Optional[str]:
    """Extract YouTube video ID from URL or return as-is if already an ID."""
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        m = re.search(pattern, url_or_id)
        if m:
            return m.group(1)
    # If it looks like a bare video ID
    if re.match(r'^[a-zA-Z0-9_-]{11}$', url_or_id):
        return url_or_id
    return None


def get_transcript(url_or_id: str, language: str = "ja") -> str:
    """Fetch YouTube transcript and return as plain text.

    Args:
        url_or_id: YouTube URL or video ID
        language: Preferred language code (default: "ja")

    Returns:
        Transcript text, or error message
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled
        from youtube_transcript_api._errors import NoTranscriptFound
    except ImportError:
        return "[YouTube] youtube-transcript-api がインストールされていません。"

    video_id = _extract_video_id(url_or_id)
    if not video_id:
        return f"[YouTube] 動画IDを解析できませんでした: {url_or_id}"

    try:
        # v1.x API: instantiate and use fetch() with language priority list
        api = YouTubeTranscriptApi()
        languages = [language, "en", "en-US", "ja"] if language not in ("en", "en-US") else ["en", "en-US", "ja"]
        fetched = api.fetch(video_id, languages=languages)
        text = " ".join(e.text for e in fetched)
        return text

    except TranscriptsDisabled:
        return f"[YouTube] この動画({video_id})ではトランスクリプトが無効化されています。"
    except Exception as e:
        return f"[YouTube] トランスクリプト取得エラー ({video_id}): {e}"


def get_transcript_with_meta(url_or_id: str, language: str = "ja") -> dict:
    """Fetch transcript with metadata (video_id, language, char count).

    Returns:
        dict with keys: video_id, url, language, text, char_count, error
    """
    video_id = _extract_video_id(url_or_id)
    result = {
        "video_id": video_id,
        "url": f"https://youtu.be/{video_id}" if video_id else url_or_id,
        "language": language,
        "text": "",
        "char_count": 0,
        "error": None,
    }

    if not video_id:
        result["error"] = f"動画IDを解析できませんでした: {url_or_id}"
        return result

    text = get_transcript(url_or_id, language)
    if text.startswith("[YouTube]"):
        result["error"] = text
    else:
        result["text"] = text
        result["char_count"] = len(text)

    return result
