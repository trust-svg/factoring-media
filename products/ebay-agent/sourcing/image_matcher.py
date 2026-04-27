"""
AI画像比較モジュール — Claude Vision で eBay出品画像と候補画像を比較
ebay-inventory-tool/image_matcher.py から移植
"""
import base64
import logging
import os

import requests

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/png,image/*;q=0.8,*/*;q=0.5",
}

# Anthropic API は最大 5MB / 8000x8000px。安全マージンで 4MB 上限。
_MAX_IMAGE_BYTES = 4 * 1024 * 1024
_ALLOWED_MEDIA = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def _download_image(url: str, timeout: int = 10) -> tuple[str, str] | None:
    """画像URLをダウンロードし (base64, media_type) を返す。失敗時 None。"""
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=timeout, headers=_BROWSER_HEADERS, stream=True)
        resp.raise_for_status()
        content = resp.content
        if len(content) > _MAX_IMAGE_BYTES:
            logger.debug(f"画像サイズ超過 ({len(content)} bytes): {url}")
            return None
        media = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if media not in _ALLOWED_MEDIA:
            media = _guess_media_from_bytes(content) or _guess_media_from_url(url)
        if media not in _ALLOWED_MEDIA:
            logger.debug(f"画像メディアタイプ不明 ({media}): {url}")
            return None
        return base64.standard_b64encode(content).decode("ascii"), media
    except Exception as e:
        logger.debug(f"画像ダウンロード失敗: {url} → {e}")
        return None


def _guess_media_from_bytes(data: bytes) -> str | None:
    """マジックバイトから画像形式を判定"""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _guess_media_from_url(url: str) -> str:
    """URLパスの拡張子から画像のメディアタイプを推定（フォールバック）"""
    from urllib.parse import urlparse
    path = urlparse(url).path.lower()
    if path.endswith(".png"):
        return "image/png"
    if path.endswith(".webp"):
        return "image/webp"
    if path.endswith(".gif"):
        return "image/gif"
    return "image/jpeg"


def compare_images(ebay_image_url: str, candidate_image_url: str) -> str:
    """
    eBay出品画像と候補商品画像をClaude Visionで比較。

    Returns:
        "yes"   — 同一商品と判定
        "maybe" — 類似しているが確信なし
        "no"    — 異なる商品
        "skip"  — 画像取得失敗等でスキップ
    """
    if not ANTHROPIC_API_KEY:
        return "skip"

    ebay_dl = _download_image(ebay_image_url)
    cand_dl = _download_image(candidate_image_url)

    if not ebay_dl or not cand_dl:
        return "skip"

    ebay_b64, ebay_media = ebay_dl
    cand_b64, cand_media = cand_dl

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 20,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": ebay_media,
                                    "data": ebay_b64,
                                },
                            },
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": cand_media,
                                    "data": cand_b64,
                                },
                            },
                            {
                                "type": "text",
                                "text": (
                                    "These are two product images. "
                                    "Is the second image the same product (same brand, same model) as the first? "
                                    "Reply ONLY with: yes, maybe, or no."
                                ),
                            },
                        ],
                    }
                ],
            },
            timeout=30,
        )
        if resp.status_code >= 400:
            body = resp.text[:300]
            logger.warning(f"画像比較API {resp.status_code}: {body}")
            return "skip"
        answer = resp.json()["content"][0]["text"].strip().lower()

        if "yes" in answer:
            return "yes"
        elif "maybe" in answer:
            return "maybe"
        else:
            return "no"

    except Exception as e:
        logger.warning(f"画像比較APIエラー: {e}")
        return "skip"
