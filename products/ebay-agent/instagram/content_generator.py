"""Instagram コンテンツ生成パイプライン

eBay出品データ → Claude AI → Instagram投稿用キャプション・ハッシュタグ
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

import anthropic

from database.models import get_db, InstagramPost
from database import crud
from instagram.prompts import INSTAGRAM_CAPTION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


async def generate_instagram_content(
    sku: str,
    content_type: str = "carousel",
    tone: str = "showcase",
) -> dict:
    """
    eBay出品データからInstagram投稿コンテンツを自動生成する。

    Args:
        sku: eBay SKU
        content_type: single / carousel / reel_script / story
        tone: showcase / educational / behind_scenes / urgency

    Returns:
        生成結果 + InstagramPost DB ID
    """
    db = get_db()
    try:
        listing = crud.get_listing(db, sku)
        if not listing:
            return {"error": f"SKU {sku} が見つかりません"}

        images = json.loads(listing.image_urls_json) if listing.image_urls_json else []
        specs = json.loads(listing.item_specifics_json) if listing.item_specifics_json else {}

        client = anthropic.Anthropic()
        prompt = f"""Generate an Instagram {content_type} post for this product.
Tone: {tone}

PRODUCT DATA:
- Title: {listing.title}
- Price: ${listing.price_usd:.2f}
- Direct purchase price (DM): ${listing.price_usd * 0.87:.2f}
- Condition: {listing.condition}
- Category: {listing.category_name}
- Specs: {json.dumps(specs, ensure_ascii=False)}
- Description excerpt: {(listing.description or '')[:500]}
- Number of photos available: {len(images)}

Remember to include both eBay link-in-bio CTA and DM direct purchase option.
Respond with JSON only."""

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=INSTAGRAM_CAPTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return {"error": "AIの応答からJSONを抽出できませんでした"}

        result = json.loads(match.group(0))

        # DB保存
        post = InstagramPost(
            sku=sku,
            caption=result.get("caption", ""),
            hashtags_json=json.dumps(result.get("hashtags", []), ensure_ascii=False),
            content_type=result.get("content_type", content_type),
            tone=tone,
            image_urls_json=json.dumps(images[:10], ensure_ascii=False),
            slide_suggestions_json=json.dumps(
                result.get("slide_suggestions", []), ensure_ascii=False
            ),
            cta=result.get("cta", ""),
            status="draft",
        )
        db.add(post)
        db.commit()

        logger.info(f"Instagram投稿ドラフト生成: SKU={sku}, ID={post.id}")

        return {
            "instagram_post_id": post.id,
            "sku": sku,
            "caption": result.get("caption", ""),
            "hashtags": result.get("hashtags", []),
            "hook_line": result.get("hook_line", ""),
            "content_type": result.get("content_type", content_type),
            "slide_suggestions": result.get("slide_suggestions", []),
            "cta": result.get("cta", ""),
            "estimated_engagement": result.get("estimated_engagement", "medium"),
            "image_count": len(images),
            "direct_price_usd": round(listing.price_usd * 0.87, 2),
            "status": "draft",
        }
    finally:
        db.close()


async def generate_sold_story(sku: str, sale_price_usd: float) -> dict:
    """売れた商品の「SOLD!」ストーリー用コンテンツ生成"""
    db = get_db()
    try:
        listing = crud.get_listing(db, sku)
        title = listing.title if listing else sku

        caption = (
            f"SOLD! 🎉\n\n"
            f"{title}\n\n"
            f"Another piece of Japanese history finds a new home! 🇯🇵✈️🌍\n\n"
            f"Follow @samuraishopjp for first access to new arrivals.\n"
            f"DM us for direct purchases — save on fees!\n\n"
            f"#samuraishopjp #sold #japanvintage #madeinjapan"
        )

        post = InstagramPost(
            sku=sku,
            caption=caption,
            hashtags_json=json.dumps([
                "samuraishopjp", "sold", "japanvintage", "madeinjapan",
                "ebayseller", "vintageaudio", "japaneseantiques",
            ]),
            content_type="story",
            tone="urgency",
            cta="Follow for new arrivals!",
            status="draft",
        )
        db.add(post)
        db.commit()

        return {
            "instagram_post_id": post.id,
            "sku": sku,
            "caption": caption,
            "content_type": "story",
            "status": "draft",
        }
    finally:
        db.close()
