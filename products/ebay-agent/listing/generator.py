"""AI出品生成エンジン（Python版）

ebay-listing-generator Chrome拡張のAI生成ロジックをPythonに移植。
サーバーサイドで出品データを生成可能にする。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import anthropic

from listing.prompts import LISTING_GENERATOR_SYSTEM_PROMPT, IMAGE_RECOGNITION_PROMPT

logger = logging.getLogger(__name__)

_DESC_TEMPLATES_DIR = Path(__file__).parent / "desc_templates"


DEFAULT_CONDITION_DESCRIPTION = (
    "This item has been tested and confirmed to be in basic working order. "
    "It is a used item, but overall it is in relatively good condition for its age. "
    "There may be minor signs of use such as small scratches, scuffs, or slight wear "
    "consistent with normal use. Please check the photos carefully, as they are part "
    "of the description. If you have any questions, feel free to contact me."
)


def load_desc_template(name: str) -> Optional[str]:
    """Load a description template by name, e.g. '001' → desc_templates/001.html.
    Returns None if the file does not exist."""
    path = _DESC_TEMPLATES_DIR / f"{name}.html"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def apply_desc_template(template_html: str, description: str, title: str = "") -> str:
    """Replace placeholders in the description template.

    - ``{description}`` / ``[[description]]`` → AI 生成 description
    - ``[[title]]`` / ``{title}`` → 出品タイトル（指定があれば）
    """
    out = template_html.replace("{description}", description)
    out = out.replace("[[description]]", description)
    if title:
        out = out.replace("[[title]]", title)
        out = out.replace("{title}", title)
    return out


async def generate_listing(
    product_name: str,
    category: str = "",
    condition: str = "",
    competitor_keywords: list[str] | None = None,
    image_base64: str = "",
    image_media_type: str = "image/jpeg",
) -> dict:
    """
    AIで最適化されたeBay出品データを生成する。

    Returns:
        {
            "titles": [{"title": str, "length": int, "strategy": str}, ...],
            "description_html": str,
            "features": [{"emoji": str, "text": str}, ...],
            "specs": dict,
            "keywords": list[str],
            "category_suggestion": str,
            "japanese_memo": str,
            ...
        }
    """
    client = anthropic.Anthropic()

    user_message = f"Generate an optimized eBay listing for: {product_name}"
    if category:
        user_message += f"\nCategory: {category}"
    if condition:
        user_message += f"\nCondition: {condition}"
    if competitor_keywords:
        user_message += f"\n\nCompetitor title keywords (incorporate for SEO): {', '.join(competitor_keywords)}"
    user_message += "\n\nRespond with JSON only."

    # コンテンツ構築
    content: list[dict] | str
    if image_base64:
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image_media_type,
                    "data": image_base64,
                },
            },
            {"type": "text", "text": user_message},
        ]
    else:
        content = user_message

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=LISTING_GENERATOR_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    text = response.content[0].text
    import re

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("AIの応答からJSONを抽出できませんでした")

    raw = match.group(0)

    # AI sometimes emits literal newlines/tabs inside JSON string values instead
    # of \\n — fix them before parsing to avoid "Expecting ',' delimiter" errors
    def _escape_str_newlines(m: re.Match) -> str:
        return m.group(0).replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")

    raw = re.sub(r'"(?:[^"\\]|\\.)*"', _escape_str_newlines, raw, flags=re.DOTALL)
    result = json.loads(raw)
    logger.info(
        f"出品生成完了: {product_name} (タイトル{len(result.get('titles', []))}件)"
    )
    return result


async def recognize_image(
    image_base64: str,
    image_media_type: str = "image/jpeg",
) -> dict:
    """商品画像からブランド・モデル・カテゴリを認識"""
    client = anthropic.Anthropic()

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=IMAGE_RECOGNITION_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": image_media_type,
                            "data": image_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Identify this product. Provide full name, brand, model, category. JSON only.",
                    },
                ],
            }
        ],
    )

    text = response.content[0].text
    import re

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("画像認識の応答を解析できませんでした")
    return json.loads(match.group(0))
