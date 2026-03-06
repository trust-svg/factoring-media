"""Claude API を使ったSEO最適化エージェント"""
from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from config import EBAY_TITLE_MAX_LENGTH
from optimizer.prompts import (
    OPTIMIZER_TOOLS,
    SEO_OPTIMIZER_SYSTEM_PROMPT,
    build_optimization_prompt,
)

logger = logging.getLogger(__name__)

MAX_LOOP_ITERATIONS = 5


async def run_optimizer(listing, score_data: dict) -> dict:
    """
    Claude API tool_use ループで出品を最適化する。

    戻り値: {
        "suggested_title": str,
        "suggested_description": str | None,
        "suggested_specifics": dict,
        "reasoning": str,
        "confidence": float,
    }
    """
    client = anthropic.Anthropic()
    prompt = build_optimization_prompt(listing, score_data)
    messages: list[dict] = [{"role": "user", "content": prompt}]

    result = {
        "suggested_title": listing.title,
        "suggested_description": None,
        "suggested_specifics": {},
        "reasoning": "",
        "confidence": 0.0,
    }

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=SEO_OPTIMIZER_SYSTEM_PROMPT,
        tools=OPTIMIZER_TOOLS,
        messages=messages,
    )

    iteration = 0
    while response.stop_reason == "tool_use" and iteration < MAX_LOOP_ITERATIONS:
        iteration += 1
        tool_results = []

        for block in response.content:
            if block.type == "tool_use":
                tool_response = _process_tool_call(
                    block.name, block.input, result
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": tool_response,
                })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=SEO_OPTIMIZER_SYSTEM_PROMPT,
            tools=OPTIMIZER_TOOLS,
            messages=messages,
        )

    # 最終テキストから reasoning を補完
    for block in response.content:
        if hasattr(block, "text") and block.text:
            if not result["reasoning"]:
                result["reasoning"] = block.text

    result["confidence"] = 0.8 if result["suggested_title"] != listing.title else 0.3

    logger.info(
        f"最適化完了: {listing.sku} "
        f"(タイトル: {len(result['suggested_title'])}文字, "
        f"ループ: {iteration}回)"
    )
    return result


def _process_tool_call(
    name: str, tool_input: dict[str, Any], result: dict
) -> str:
    """ツール呼び出しを処理し、結果をresultに蓄積する"""

    if name == "suggest_title":
        new_title = tool_input.get("new_title", "")
        reasoning = tool_input.get("reasoning", "")

        # バリデーション: 80文字制限
        if len(new_title) > EBAY_TITLE_MAX_LENGTH:
            return json.dumps({
                "error": (
                    f"Title is {len(new_title)} characters, "
                    f"but the maximum is {EBAY_TITLE_MAX_LENGTH}. "
                    f"Please shorten the title to {EBAY_TITLE_MAX_LENGTH} characters or fewer."
                )
            })

        result["suggested_title"] = new_title
        if reasoning:
            result["reasoning"] += f"Title: {reasoning}\n"
        return json.dumps({
            "status": "accepted",
            "char_count": len(new_title),
            "message": f"Title accepted ({len(new_title)} chars)",
        })

    elif name == "suggest_description":
        new_desc = tool_input.get("new_description", "")
        reasoning = tool_input.get("reasoning", "")

        result["suggested_description"] = new_desc
        if reasoning:
            result["reasoning"] += f"Description: {reasoning}\n"
        return json.dumps({
            "status": "accepted",
            "char_count": len(new_desc),
        })

    elif name == "suggest_item_specifics":
        specifics = tool_input.get("specifics", {})
        reasoning = tool_input.get("reasoning", "")

        result["suggested_specifics"].update(specifics)
        if reasoning:
            result["reasoning"] += f"Item Specifics: {reasoning}\n"
        return json.dumps({
            "status": "accepted",
            "specifics_count": len(specifics),
        })

    return json.dumps({"error": f"Unknown tool: {name}"})
