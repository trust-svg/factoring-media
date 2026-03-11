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


def _download_image_b64(url: str, timeout: int = 10) -> str | None:
    """画像URLをダウンロードしてbase64文字列を返す"""
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return base64.standard_b64encode(resp.content).decode("ascii")
    except Exception as e:
        logger.debug(f"画像ダウンロード失敗: {url} → {e}")
        return None


def _get_media_type(url: str) -> str:
    """URLから画像のメディアタイプを推定"""
    lower = url.lower()
    if ".png" in lower:
        return "image/png"
    if ".webp" in lower:
        return "image/webp"
    if ".gif" in lower:
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

    ebay_b64 = _download_image_b64(ebay_image_url)
    cand_b64 = _download_image_b64(candidate_image_url)

    if not ebay_b64 or not cand_b64:
        return "skip"

    ebay_media = _get_media_type(ebay_image_url)
    cand_media = _get_media_type(candidate_image_url)

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
        resp.raise_for_status()
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
