"""Claude EN⇔JA 翻訳サービス"""
from __future__ import annotations

import logging

import anthropic

logger = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


TRANSLATE_SYSTEM = """You are a professional translator for eBay buyer-seller communication.
Translate naturally and accurately. Preserve the tone (polite, casual, urgent).
Do NOT add explanations — return ONLY the translated text.
For eBay-specific terms (tracking number, refund, return, etc.), use standard translations."""


async def translate_to_ja(text: str) -> str:
    """任意の言語→日本語翻訳（Haiku高速モデル）"""
    if not text.strip():
        return ""
    try:
        resp = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            system=TRANSLATE_SYSTEM,
            messages=[{"role": "user", "content": f"Translate this eBay message to Japanese:\n\n{text}"}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        logger.error(f"翻訳エラー (→JA): {e}")
        return ""


async def translate_to_en(text: str) -> str:
    """日本語→英語翻訳"""
    if not text.strip():
        return ""
    try:
        resp = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=TRANSLATE_SYSTEM,
            messages=[{"role": "user", "content": f"Translate this Japanese message to English for an eBay buyer:\n\n{text}"}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        logger.error(f"翻訳エラー (JA→EN): {e}")
        return f"[Translation error] {text}"


async def suggest_alternatives(text: str, lang: str = "en") -> list[str]:
    """表現の代替案を3つ提案"""
    try:
        prompt = f"Provide 3 alternative ways to say this in {'English' if lang == 'en' else 'Japanese'} for eBay communication. Return each on a new line, numbered 1-3. No explanations.\n\n{text}"
        resp = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system="You are a professional eBay communication assistant.",
            messages=[{"role": "user", "content": prompt}],
        )
        lines = [l.strip() for l in resp.content[0].text.strip().split("\n") if l.strip()]
        # 番号プレフィックスを除去
        alternatives = []
        for line in lines[:3]:
            cleaned = line.lstrip("0123456789.-) ").strip()
            if cleaned:
                alternatives.append(cleaned)
        return alternatives
    except Exception as e:
        logger.error(f"代替案生成エラー: {e}")
        return []
