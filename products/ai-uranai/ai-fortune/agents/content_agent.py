"""Threads投稿生成エージェント（Claude tool_use パターン）"""

import json
import random
from datetime import date, timedelta
from typing import Any

import anthropic

from database.crud import AsyncSessionLocal, get_recent_posts, record_threads_post
from prompts.threads_content import (
    AFTERNOON_THEME_PROMPT,
    EVENING_THEME_PROMPT,
    MORNING_THEME_PROMPT,
    THREADS_CONTENT_SYSTEM_PROMPT,
)
from threads.api import ThreadsClient

TAROT_CARDS: list[str] = [
    "愚者", "魔術師", "女教皇", "女帝", "皇帝", "法王",
    "恋人", "戦車", "力", "隠者", "運命の輪", "正義",
    "吊るされた男", "死神", "節制", "悪魔", "塔", "星",
    "月", "太陽", "審判", "世界",
]

CONTENT_TOOLS: list[dict] = [
    {
        "name": "get_content_theme",
        "description": "投稿スロット（朝/昼/夜）に応じたテーマプロンプトを取得する",
        "input_schema": {
            "type": "object",
            "properties": {
                "post_slot": {
                    "type": "string",
                    "enum": ["morning", "afternoon", "evening"],
                    "description": "投稿スロット",
                },
            },
            "required": ["post_slot"],
        },
    },
    {
        "name": "get_recent_post_themes",
        "description": "過去N日分の投稿テーマを取得して重複を防ぐ",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "遡る日数",
                    "default": 7,
                },
            },
            "required": ["days"],
        },
    },
    {
        "name": "publish_to_threads",
        "description": "Threads APIを使って投稿を公開する",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "投稿テキスト（280文字以内、ハッシュタグ含む）",
                },
                "theme": {"type": "string", "description": "投稿テーマ（DB記録用）"},
                "post_slot": {
                    "type": "string",
                    "enum": ["morning", "afternoon", "evening"],
                },
            },
            "required": ["text", "theme", "post_slot"],
        },
    },
]


async def _execute_content_tool(name: str, tool_input: dict[str, Any]) -> str:
    today = date.today()
    tomorrow = today + timedelta(days=1)

    if name == "get_content_theme":
        slot = tool_input["post_slot"]
        if slot == "morning":
            return MORNING_THEME_PROMPT.format(date=today.strftime("%Y年%m月%d日"))
        elif slot == "afternoon":
            card = random.choice(TAROT_CARDS)
            position = random.choice(["正位置", "逆位置"])
            return AFTERNOON_THEME_PROMPT.format(card_name=card, position=position)
        else:  # evening
            return EVENING_THEME_PROMPT.format(tomorrow=tomorrow.strftime("%Y年%m月%d日"))

    elif name == "get_recent_post_themes":
        days = tool_input.get("days", 7)
        async with AsyncSessionLocal() as session:
            posts = await get_recent_posts(session, days)
            themes = [p.theme for p in posts]
        return json.dumps({"recent_themes": themes, "count": len(themes)})

    elif name == "publish_to_threads":
        threads_client = ThreadsClient()
        post_id = await threads_client.create_text_post(tool_input["text"])
        async with AsyncSessionLocal() as session:
            await record_threads_post(
                session,
                theme=tool_input["theme"],
                content=tool_input["text"],
                post_slot=tool_input["post_slot"],
                threads_post_id=post_id,
            )
        return json.dumps({"status": "published", "post_id": post_id})

    return json.dumps({"error": f"Unknown tool: {name}"})


async def run_content_agent(post_slot: str) -> str:
    """
    ContentAgent のエントリーポイント。
    post_slot: "morning" | "afternoon" | "evening"
    """
    client = anthropic.Anthropic()

    user_message = (
        f"投稿スロット「{post_slot}」のThreads投稿を作成して公開してください。\n"
        "まず過去7日間のテーマを確認してから、重複しないテーマで投稿を作成してください。\n"
        "投稿が完了したら結果を教えてください。"
    )

    messages: list[dict] = [{"role": "user", "content": user_message}]

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        system=THREADS_CONTENT_SYSTEM_PROMPT,
        tools=CONTENT_TOOLS,
        messages=messages,
    )

    while response.stop_reason == "tool_use":
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = await _execute_content_tool(block.name, block.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            system=THREADS_CONTENT_SYSTEM_PROMPT,
            tools=CONTENT_TOOLS,
            messages=messages,
        )

    return " ".join(
        block.text for block in response.content if hasattr(block, "text")
    ).strip()
