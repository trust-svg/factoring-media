"""Agent Team — specialized AI agents for eBay listing optimization.

Research Agent: eBay demand analysis, category, competitive pricing
Quality Agent: condition evaluation from images + description
Listing Agent: title, description, item specifics generation
Pricing Agent: optimal price calculation (no AI, pure math)
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import sys
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


# ── Research Agent ───────────────────────────────────────

async def research_agent(product_name: str, condition: str = "") -> dict:
    """Analyze eBay demand, find optimal category, competitive pricing.

    Uses eBay Browse API for data, then Claude for analysis.
    Returns: category_id, avg_price_usd, competitor_keywords, demand_level,
             recommended_condition_enum
    """
    # Step 1: Get eBay data (no AI needed)
    ebay_data = _search_ebay(product_name)
    items = ebay_data.get("items", [])
    total = ebay_data.get("total", 0)

    if not items:
        # Fallback: return minimal data
        return {
            "category_id": "",
            "avg_price_usd": 0,
            "competitor_keywords": [],
            "demand_level": "unknown",
            "recommended_condition_enum": "USED_VERY_GOOD",
        }

    # Step 2: Analyze with Claude
    prices = [i["price"] for i in items if i.get("price", 0) > 0]
    avg_price = sum(prices) / len(prices) if prices else 0
    titles = [i.get("title", "") for i in items[:10]]
    categories = [i.get("category_id", "") for i in items if i.get("category_id")]
    conditions = [i.get("condition", "") for i in items if i.get("condition")]

    prompt = f"""Analyze this eBay market data for: {product_name}
Condition: {condition or 'Used'}

Active listings: {total}
Average price: ${avg_price:.0f}
Sample titles: {json.dumps(titles[:5])}
Categories seen: {json.dumps(list(set(categories))[:5])}
Conditions seen: {json.dumps(list(set(conditions))[:5])}

Respond in JSON only:
{{
  "category_id": "most common eBay category ID from the data",
  "avg_price_usd": {avg_price:.0f},
  "competitor_keywords": ["top 5 SEO keywords extracted from competitor titles"],
  "demand_level": "high/medium/low based on total listings",
  "recommended_condition_enum": "USED_VERY_GOOD or appropriate eBay enum"
}}"""

    try:
        result = await _call_claude(prompt, max_tokens=500)
        data = _parse_json(result)
        if data:
            data.setdefault("avg_price_usd", avg_price)
            return data
    except Exception as e:
        logger.error(f"Research agent error: {e}")

    # Fallback
    most_common_cat = max(set(categories), key=categories.count) if categories else ""
    return {
        "category_id": most_common_cat,
        "avg_price_usd": round(avg_price, 2),
        "competitor_keywords": [],
        "demand_level": "medium" if total > 50 else "low",
        "recommended_condition_enum": "USED_VERY_GOOD",
    }


# ── Quality Agent ────────────────────────────────────────

async def quality_agent(
    description_jp: str,
    condition_text: str,
    image_urls: Optional[list] = None,
) -> dict:
    """Evaluate item condition from images and Japanese description.

    Returns: ebay_condition, condition_notes_en, defects, overall_score
    """
    # Build prompt with image if available
    image_b64 = ""
    if image_urls:
        image_b64 = await _download_image_b64(image_urls[0])

    prompt = f"""Evaluate this item's condition for eBay listing.

Japanese description:
{description_jp[:1000]}

Condition label from source: {condition_text}

Based on the description (and image if provided), provide:
1. Appropriate eBay condition enum
2. English condition notes for the listing
3. Any defects mentioned
4. Overall quality score 1-10

Respond in JSON only:
{{
  "ebay_condition": "USED_VERY_GOOD",
  "condition_notes_en": "Item is in good working condition with minor cosmetic wear...",
  "defects": ["list of any defects mentioned"],
  "overall_score": 7
}}"""

    try:
        result = await _call_claude(prompt, max_tokens=500, image_b64=image_b64)
        data = _parse_json(result)
        if data:
            return data
    except Exception as e:
        logger.error(f"Quality agent error: {e}")

    # Fallback
    return {
        "ebay_condition": "USED_VERY_GOOD",
        "condition_notes_en": "Item is in used condition. Please see photos for details.",
        "defects": [],
        "overall_score": 6,
    }


# ── Listing Agent ────────────────────────────────────────

async def listing_agent(
    product_name: str,
    condition: str,
    research: dict,
    quality: dict,
    description_jp: str = "",
    image_b64: str = "",
) -> dict:
    """Generate optimized eBay listing data.

    Returns: title, description_html, specs, category_id
    """
    competitor_kws = research.get("competitor_keywords", [])
    condition_notes = quality.get("condition_notes_en", "")
    defects = quality.get("defects", [])
    category_id = research.get("category_id", "")

    prompt = f"""Generate an optimized eBay listing for: {product_name}

Condition: {condition}
Condition details: {condition_notes}
Defects: {json.dumps(defects) if defects else 'None'}
Competitor keywords to include: {', '.join(competitor_kws)}
Japanese source description: {description_jp[:800]}

TITLE RULES:
- 75-80 characters max
- Structure: Brand + Model + Key Features + Condition
- ALWAYS end with "JAPAN"
- Front-load brand + model

DESCRIPTION: English only, HTML with <br>, <b>, emoji, 【】headers.
Structure: Features → Why Popular → Condition → Included Items → Shipping

SPECS: 8-12+ fields using standard eBay names (Brand, Model, Type, etc.)

Respond in JSON only:
{{
  "title": "Best title (75-80 chars, ends with JAPAN)",
  "description_html": "Full HTML description",
  "specs": {{"Brand": "...", "Model": "...", ...}},
  "category_id": "{category_id}"
}}"""

    try:
        result = await _call_claude(
            prompt, max_tokens=4000, image_b64=image_b64,
        )
        data = _parse_json(result)
        if data:
            data.setdefault("category_id", category_id)
            return data
    except Exception as e:
        logger.error(f"Listing agent error: {e}")

    # Fallback: minimal listing
    return {
        "title": f"{product_name} Used From JAPAN"[:80],
        "description_html": f"<b>{product_name}</b><br><br>{condition_notes}<br><br>Shipped from Japan with tracking.",
        "specs": {"Brand": product_name.split()[0] if product_name else ""},
        "category_id": category_id,
    }


# ── Pricing Agent (no AI) ───────────────────────────────

def pricing_agent(
    purchase_price_jpy: int,
    research: dict,
    min_profit_jpy: int = 0,
    min_margin: float = 0,
) -> dict:
    """Calculate optimal price. Pure math, no Claude API call.

    Returns: price_usd, profit_jpy, margin, constraint
    """
    from discovery import calc_optimal_price, _get_exchange_rate

    rate = _get_exchange_rate()
    result = calc_optimal_price(
        purchase_price_jpy=purchase_price_jpy,
        rate=rate,
        min_profit_jpy=min_profit_jpy,
        min_margin=min_margin,
    )

    # If research has competitor pricing, adjust up toward market
    avg_competitor = research.get("avg_price_usd", 0)
    if avg_competitor > 0 and avg_competitor > result["price_usd"]:
        # Price between our floor and competitor average (slightly below competitor)
        market_price = avg_competitor * 0.95
        if market_price > result["price_usd"]:
            from discovery import _calc_profit
            market_profit = _calc_profit(market_price, purchase_price_jpy, rate)
            if market_profit >= (min_profit_jpy or 15000):
                result = {
                    "price_usd": round(market_price, 2),
                    "profit_jpy": round(market_profit),
                    "margin": round(market_profit / (market_price * rate), 3) if market_price > 0 else 0,
                    "constraint": "market",
                }

    return result


# ── Agent Team Orchestrator ──────────────────────────────

async def run_agent_team(
    product_name: str,
    purchase_price_jpy: int,
    condition: str = "",
    description_jp: str = "",
    image_urls: Optional[list] = None,
    min_profit_jpy: int = 0,
    min_margin: float = 0,
) -> dict:
    """Run full agent team pipeline.

    Phase 1 (parallel): Research Agent + Quality Agent
    Phase 2 (sequential): Pricing Agent → Listing Agent

    Returns: {"research", "quality", "pricing", "listing"}
    """
    logger.info(f"Agent team started: {product_name}")

    # Phase 1: parallel
    research_task = asyncio.create_task(research_agent(product_name, condition))
    quality_task = asyncio.create_task(
        quality_agent(description_jp, condition, image_urls)
    )
    research, quality = await asyncio.gather(research_task, quality_task)
    logger.info(f"Phase 1 done: category={research.get('category_id')}, score={quality.get('overall_score')}")

    # Phase 2: sequential
    pricing = pricing_agent(purchase_price_jpy, research, min_profit_jpy, min_margin)
    logger.info(f"Pricing: ${pricing['price_usd']} (profit ¥{pricing['profit_jpy']:,})")

    # Download first image for listing agent
    img_b64 = ""
    if image_urls:
        img_b64 = await _download_image_b64(image_urls[0])

    listing = await listing_agent(
        product_name, condition, research, quality, description_jp, img_b64,
    )
    logger.info(f"Listing generated: {listing.get('title', '')[:50]}")

    return {
        "research": research,
        "quality": quality,
        "pricing": pricing,
        "listing": listing,
    }


# ── Helpers ──────────────────────────────────────────────

def _search_ebay(query: str) -> dict:
    """Search eBay via Browse API. Returns {items, total}."""
    try:
        # Import with config collision handling
        _ebay_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ebay_core")
        if not os.path.isdir(_ebay_dir):
            parent = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ebay-agent")
            if os.path.isdir(os.path.join(parent, "ebay_core")) and parent not in sys.path:
                sys.path.insert(0, parent)

        from discovery import _import_ebay_client
        search_fn, _ = _import_ebay_client()
        return search_fn(query, limit=20)
    except Exception as e:
        logger.error(f"eBay search failed: {e}")
        return {"items": [], "total": 0}


async def _call_claude(
    prompt: str,
    max_tokens: int = 1000,
    image_b64: str = "",
) -> str:
    """Call Claude API with optional image."""
    import anthropic

    client = anthropic.Anthropic()

    if image_b64:
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_b64,
                },
            },
            {"type": "text", "text": prompt},
        ]
    else:
        content = prompt

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": content}],
    )
    return response.content[0].text


def _parse_json(text: str) -> Optional[dict]:
    """Extract JSON from Claude response."""
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


async def _download_image_b64(url: str) -> str:
    """Download image and return as base64 string."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return base64.b64encode(resp.content).decode()
    except Exception as e:
        logger.warning(f"Image download failed: {e}")
    return ""
