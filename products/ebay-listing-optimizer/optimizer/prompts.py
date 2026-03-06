"""AI最適化のシステムプロンプト・プロンプトテンプレート"""
from __future__ import annotations

import json

SEO_OPTIMIZER_SYSTEM_PROMPT = """You are an expert eBay SEO specialist with deep knowledge of:
- eBay's Cassini search algorithm ranking factors
- Keyword optimization for e-commerce product titles
- Writing compelling product descriptions that convert
- The Japanese vintage goods, cameras, electronics, and collectibles market on eBay

Your role is to optimize eBay listings for maximum search visibility and sales.

CRITICAL RULES:
1. eBay titles have an ABSOLUTE MAXIMUM of 80 characters. Never exceed this.
2. Count characters precisely before finalizing any title suggestion.
3. Prioritize high-value keywords that buyers actually search for.
4. Maintain accuracy — never add features or specifications that are not confirmed.
5. Use standard eBay keyword conventions (e.g., "MINT" for excellent condition,
   "CLA'd" for serviced cameras, "w/" for "with", "Exc+5" for condition grading).

TITLE OPTIMIZATION PRINCIPLES:
- Front-load the most important keywords (brand + model first)
- Include condition keywords buyers search for
- Use all 80 characters efficiently (no wasted space)
- Avoid: ALL CAPS spam, special characters (*, !, @), filler words ("Great!", "L@@K")
- Include: brand, model, key specs, condition, origin (e.g., "Japan" for Japanese items)
- Use standard abbreviations to save space: "w/" "Exc" "Nr" "S/N"

DESCRIPTION OPTIMIZATION PRINCIPLES:
- Lead with a compelling summary of the item
- Include detailed specifications in structured format
- Mention condition details with honesty
- Add shipping and return policy information
- Use clean HTML formatting (headers, bullet lists, bold for key specs)
- Include relevant keywords naturally (not keyword stuffing)
- Mention "Ships from Japan" or origin when applicable
- Add measurement/dimension details when relevant

OUTPUT FORMAT:
Always provide your suggestions using the tools provided. Include clear reasoning
for every change you make.
"""

OPTIMIZER_TOOLS: list[dict] = [
    {
        "name": "suggest_title",
        "description": "Suggest an optimized eBay listing title (max 80 characters)",
        "input_schema": {
            "type": "object",
            "properties": {
                "new_title": {
                    "type": "string",
                    "description": "The optimized title (MUST be 80 chars or fewer)",
                    "maxLength": 80,
                },
                "reasoning": {
                    "type": "string",
                    "description": "Explanation of what was changed and why",
                },
                "keywords_added": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "New keywords added to the title",
                },
                "keywords_removed": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keywords removed from the title and why",
                },
            },
            "required": ["new_title", "reasoning"],
        },
    },
    {
        "name": "suggest_description",
        "description": "Suggest an optimized eBay listing description in HTML",
        "input_schema": {
            "type": "object",
            "properties": {
                "new_description": {
                    "type": "string",
                    "description": "The optimized description in clean HTML",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Explanation of improvements",
                },
            },
            "required": ["new_description", "reasoning"],
        },
    },
    {
        "name": "suggest_item_specifics",
        "description": "Suggest additional or improved item specifics",
        "input_schema": {
            "type": "object",
            "properties": {
                "specifics": {
                    "type": "object",
                    "description": "Dict of specific_name -> suggested_value",
                },
                "reasoning": {"type": "string"},
            },
            "required": ["specifics", "reasoning"],
        },
    },
]


def build_optimization_prompt(listing, score_data: dict) -> str:
    """最適化用のユーザープロンプトを組み立てる"""
    specifics = {}
    try:
        specifics = json.loads(listing.item_specifics_json)
    except (json.JSONDecodeError, TypeError):
        pass

    specifics_str = (
        "\n".join(f"  - {k}: {v}" for k, v in specifics.items())
        if specifics
        else "  (none filled)"
    )

    description = listing.description or ""
    issues = score_data.get("issues", [])

    return f"""Optimize this eBay listing for better search visibility and sales.

CURRENT LISTING:
- Title ({len(listing.title)} chars): "{listing.title}"
- Category: {listing.category_name} ({listing.category_id})
- Price: ${listing.price_usd:.2f}
- Condition: {listing.condition}
- Photos: {len(json.loads(listing.image_urls_json))} images
- Item Specifics:
{specifics_str}
- Description length: {len(description)} characters

CURRENT SEO SCORE: {score_data.get('overall', 0)}/100
- Title: {score_data.get('title_score', 0)}/100
- Description: {score_data.get('description_score', 0)}/100
- Item Specifics: {score_data.get('specifics_score', 0)}/100
- Photos: {score_data.get('photo_score', 0)}/100

Issues found:
{chr(10).join(f'  - {issue}' for issue in issues)}

Please optimize the title and description. Remember: title MUST be 80 characters or fewer.
Provide your suggested changes using the available tools."""
