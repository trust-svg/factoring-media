"""eBay AI Agent オーケストレーター

Claude tool_use パターンで全ツールを自律的に呼び出す統合AIエージェント。
自然言語の指示を受けて、適切なツールを選択・実行し、結果を返す。
"""
from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from tools.handlers import handle_tool_call
from tools.registry import AGENT_TOOLS, DESTRUCTIVE_TOOLS

logger = logging.getLogger(__name__)

AGENT_SYSTEM_PROMPT = """あなたはeBay輸出ビジネスの統合AIアシスタントです。
日本からの越境EC（eBay）運営を支援する専門エージェントとして、以下の機能を提供します：

1. **在庫管理**: eBay出品の在庫状況を確認し、在庫切れアイテムを検出
2. **仕入れ検索**: 日本のマーケットプレイス（ヤフオク、メルカリ等）で仕入れ候補を検索
3. **出品生成**: AIでSEO最適化されたeBay出品タイトル・説明文を生成
4. **SEO分析**: 既存出品のSEOスコアを分析し、改善点を提示
5. **出品最適化**: AIで出品タイトル・説明文を最適化
6. **競合分析**: eBayで競合商品を検索・分析
7. **価格分析**: 競合価格を分析し、最適価格を提案
8. **利益計算**: 仕入れ価格と販売価格から利益率を算出
9. **為替レート**: 最新のUSD→JPY為替レートを取得
10. **仕入れ管理**: 日本マーケットプレイスでの購入実績を記録・追跡し、正確な利益計算を実現

重要なルール:
- eBayタイトルは80文字以内
- eBay手数料は12.9%で計算
- 破壊的操作（出品更新）の前には必ず確認を取ること
- 日本語と英語の両方で対応可能
- 具体的なデータに基づいた提案を心がけること
"""

MAX_AGENT_ITERATIONS = 10


async def run_agent(user_message: str) -> dict:
    """
    自然言語の指示を受けて、ツールを自律的に実行するAIエージェント。

    Returns:
        {
            "response": str,         # エージェントの最終回答
            "tool_calls": list,      # 実行したツール呼び出しログ
            "iterations": int,       # ループ回数
        }
    """
    client = anthropic.Anthropic()
    messages: list[dict] = [{"role": "user", "content": user_message}]
    tool_call_log: list[dict] = []

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=AGENT_SYSTEM_PROMPT,
        tools=AGENT_TOOLS,
        messages=messages,
    )

    iteration = 0
    while response.stop_reason == "tool_use" and iteration < MAX_AGENT_ITERATIONS:
        iteration += 1
        tool_results = []

        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input

                logger.info(f"Agent tool call [{iteration}]: {tool_name}({json.dumps(tool_input, ensure_ascii=False)[:200]})")

                # 破壊的ツールのチェック（API経由の場合はスキップ、CLIの場合は確認）
                if tool_name in DESTRUCTIVE_TOOLS:
                    logger.warning(f"破壊的ツール実行: {tool_name}")

                result = await handle_tool_call(tool_name, tool_input)
                tool_call_log.append({
                    "tool": tool_name,
                    "input": tool_input,
                    "output_preview": result[:500] if len(result) > 500 else result,
                })
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=AGENT_SYSTEM_PROMPT,
            tools=AGENT_TOOLS,
            messages=messages,
        )

    # 最終テキスト応答を抽出
    final_text = ""
    for block in response.content:
        if hasattr(block, "text") and block.text:
            final_text += block.text

    logger.info(f"Agent completed: {iteration} iterations, {len(tool_call_log)} tool calls")

    return {
        "response": final_text,
        "tool_calls": tool_call_log,
        "iterations": iteration,
    }
