"""AI リサーチエージェント

自然言語の指示で需要分析を行うClaude tool_useエージェント。
「ビンテージシンセサイザーで利益が出る商品を見つけて」のような指示に対応。
"""
from __future__ import annotations

import json
import logging

import anthropic

from research.demand import analyze_demand, compare_categories

logger = logging.getLogger(__name__)

RESEARCH_SYSTEM_PROMPT = """あなたはeBay輸出ビジネスの市場リサーチ専門AIエージェントです。

あなたの役割:
- ユーザーの指示に基づいてeBayの需要・競合を分析する
- 日本から仕入れて利益が出る商品を特定する
- データに基づいた具体的な推奨を提供する

重要なルール:
1. 必ずツールを使ってデータを収集してから回答する
2. 推定仕入れ価格、利益率、需要スコアを必ず含める
3. 日本語で回答する
4. 具体的な商品名・価格を含むアクション可能な提案をする
5. 「Japan quality premium」（日本品質プレミアム: +5〜15%）を考慮する

出力フォーマット:
- 市場概要（サイズ、価格帯、競合数）
- 有望商品リスト（トップ5）
- 推奨アクション（仕入れ→出品の具体的ステップ）
"""

RESEARCH_TOOLS = [
    {
        "name": "analyze_market",
        "description": "指定キーワードのeBay市場需要を分析する。売れ筋度、価格帯、推定利益率を返す。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "検索キーワード（英語）。例: 'vintage synthesizer', 'Pioneer CDJ'",
                },
                "max_source_price_jpy": {
                    "type": "integer",
                    "description": "仕入れ上限（円）",
                    "default": 50000,
                },
                "limit": {
                    "type": "integer",
                    "description": "検索件数上限",
                    "default": 50,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "compare_markets",
        "description": "複数のカテゴリ/キーワードを比較分析し、最も有望な市場をランキングする。",
        "input_schema": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "比較するキーワードリスト（英語）",
                },
                "limit": {
                    "type": "integer",
                    "description": "各検索の件数上限",
                    "default": 30,
                },
            },
            "required": ["queries"],
        },
    },
    {
        "name": "report_findings",
        "description": "リサーチ結果をまとめたレポートを出力する。必ず最後にこのツールを呼ぶこと。",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary_ja": {
                    "type": "string",
                    "description": "日本語のリサーチサマリー",
                },
                "top_opportunities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product": {"type": "string"},
                            "estimated_sell_price_usd": {"type": "number"},
                            "estimated_source_price_jpy": {"type": "integer"},
                            "estimated_margin_pct": {"type": "number"},
                            "demand_level": {"type": "string", "enum": ["high", "medium", "low"]},
                            "action": {"type": "string"},
                        },
                    },
                    "description": "上位の機会リスト",
                },
                "recommended_next_steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "推奨アクション（日本語）",
                },
            },
            "required": ["summary_ja", "top_opportunities", "recommended_next_steps"],
        },
    },
]

MAX_ITERATIONS = 8


def _handle_research_tool(name: str, tool_input: dict) -> str:
    """リサーチツールの実処理"""
    if name == "analyze_market":
        result = analyze_demand(
            query=tool_input["query"],
            max_source_price_jpy=tool_input.get("max_source_price_jpy", 50000),
            limit=tool_input.get("limit", 50),
        )
        return json.dumps(result, ensure_ascii=False, default=str)

    elif name == "compare_markets":
        result = compare_categories(
            queries=tool_input["queries"],
            limit=tool_input.get("limit", 30),
        )
        return json.dumps(result, ensure_ascii=False, default=str)

    elif name == "report_findings":
        return json.dumps(tool_input, ensure_ascii=False)

    return json.dumps({"error": f"Unknown tool: {name}"})


async def run_research_agent(instruction: str) -> dict:
    """
    自然言語の指示で市場リサーチを実行する。

    Args:
        instruction: リサーチ指示（日本語OK）
            例: 「ビンテージシンセサイザーで利益が出る商品を見つけて」

    Returns:
        {
            "response": str,  # AIの回答テキスト
            "findings": dict | None,  # report_findingsの結果
            "tool_calls": list,  # 使用したツールのログ
            "iterations": int,
        }
    """
    client = anthropic.Anthropic()

    messages = [{"role": "user", "content": instruction}]
    tool_calls_log = []
    findings = None

    for iteration in range(MAX_ITERATIONS):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=RESEARCH_SYSTEM_PROMPT,
            tools=RESEARCH_TOOLS,
            messages=messages,
        )

        # ツール呼び出しがない場合は完了
        if response.stop_reason != "tool_use":
            text_parts = [b.text for b in response.content if b.type == "text"]
            return {
                "response": "\n".join(text_parts),
                "findings": findings,
                "tool_calls": tool_calls_log,
                "iterations": iteration + 1,
            }

        # ツール呼び出し処理
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_calls_log.append({
                    "tool": block.name,
                    "input_summary": str(block.input)[:200],
                })

                result_str = _handle_research_tool(block.name, block.input)

                # report_findings の結果を保存
                if block.name == "report_findings":
                    findings = block.input

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str,
                })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    return {
        "response": "リサーチが最大イテレーション数に達しました。",
        "findings": findings,
        "tool_calls": tool_calls_log,
        "iterations": MAX_ITERATIONS,
    }
