"""eBay Agent Hub — MCP Server

全機能をModel Context Protocol (MCP) で公開し、
Claude Desktop や Claude Code から直接eBay操作を可能にする。

Usage:
    python mcp_server.py

Claude Desktop 設定 (~/.claude/claude_desktop_config.json):
    {
        "mcpServers": {
            "ebay-agent": {
                "command": "python",
                "args": ["/path/to/mcp_server.py"],
                "env": {
                    "EBAY_CLIENT_ID": "...",
                    "EBAY_CLIENT_SECRET": "...",
                    "ANTHROPIC_API_KEY": "..."
                }
            }
        }
    }
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("ebay-mcp")

# MCP SDK の有無を確認
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    HAS_MCP = True
except ImportError:
    HAS_MCP = False
    logger.warning("mcp パッケージが見つかりません。pip install mcp でインストールしてください。")

# DB初期化
from database.models import init_db
init_db()

# ツール定義とハンドラーをインポート
from tools.registry import AGENT_TOOLS, DESTRUCTIVE_TOOLS
from tools.handlers import handle_tool_call


def _convert_to_mcp_tools() -> list[dict]:
    """AGENT_TOOLS を MCP Tool 形式に変換"""
    mcp_tools = []
    for tool in AGENT_TOOLS:
        description = tool["description"]
        if tool["name"] in DESTRUCTIVE_TOOLS:
            description = f"[⚠️ 破壊的操作] {description}"

        mcp_tools.append({
            "name": f"ebay_{tool['name']}",
            "description": description,
            "inputSchema": tool["input_schema"],
        })
    return mcp_tools


async def _handle_mcp_tool(name: str, arguments: dict) -> str:
    """MCP ツール名を内部ツール名に変換して実行"""
    # "ebay_" プレフィックスを除去
    internal_name = name.removeprefix("ebay_")
    result = await handle_tool_call(internal_name, arguments)
    return result


def run_mcp_server():
    """MCP サーバーを起動"""
    if not HAS_MCP:
        print("Error: mcp パッケージが必要です。")
        print("  pip install mcp")
        sys.exit(1)

    server = Server("ebay-agent-hub")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        tools = []
        for tool_def in _convert_to_mcp_tools():
            tools.append(Tool(
                name=tool_def["name"],
                description=tool_def["description"],
                inputSchema=tool_def["inputSchema"],
            ))
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        try:
            result_str = await _handle_mcp_tool(name, arguments)
            result_data = json.loads(result_str)

            # 破壊的操作の警告
            internal_name = name.removeprefix("ebay_")
            if internal_name in DESTRUCTIVE_TOOLS:
                result_data["_warning"] = "⚠️ この操作は破壊的です。eBayに変更が適用されます。"

            return [TextContent(
                type="text",
                text=json.dumps(result_data, ensure_ascii=False, indent=2),
            )]
        except Exception as e:
            logger.exception(f"Tool {name} failed")
            return [TextContent(
                type="text",
                text=json.dumps({"error": str(e)}, ensure_ascii=False),
            )]

    async def main():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    logger.info("eBay Agent Hub MCP Server 起動中...")
    logger.info(f"登録ツール数: {len(AGENT_TOOLS)}")
    asyncio.run(main())


# ── フォールバック: MCP なしでもツール一覧を確認可能 ──────

def print_tools():
    """登録されているツールの一覧を表示"""
    print("eBay Agent Hub — 登録ツール一覧")
    print("=" * 60)
    for tool in AGENT_TOOLS:
        prefix = "⚠️ " if tool["name"] in DESTRUCTIVE_TOOLS else "  "
        print(f"{prefix}{tool['name']:30s} {tool['description'][:60]}")
    print(f"\n合計: {len(AGENT_TOOLS)} ツール")
    print(f"破壊的ツール: {', '.join(DESTRUCTIVE_TOOLS)}")


if __name__ == "__main__":
    if "--list" in sys.argv:
        print_tools()
    elif HAS_MCP:
        run_mcp_server()
    else:
        print("MCP パッケージが見つかりません。")
        print("  pip install mcp")
        print()
        print("ツール一覧を表示: python mcp_server.py --list")
        print_tools()
