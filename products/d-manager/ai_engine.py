"""Secretary engine — Claude Code CLI or API for Discord integration.

Modes (set via ENGINE_MODE env var):
  "cli"  — Use `claude -p` (subscription, no API cost) [default]
  "api"  — Use Anthropic API (pay-per-use, fallback)
"""

import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import config
from departments import load_department_prompt

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

# Engine mode: "cli" (subscription) or "api" (pay-per-use fallback)
ENGINE_MODE = os.getenv("ENGINE_MODE", "cli")

# Company data directory for CLI mode file access instructions
COMPANY_DIR = config.COMPANY_DIR

# ---------------------------------------------------------------------------
# Shared: system prompt builder
# ---------------------------------------------------------------------------

IDENTITY_PREFIX = """## 最重要ルール
あなたはTrustLinkのAI社員です。以下のCLAUDE.mdで定義された人格として振る舞ってください。
- あなたは「外部のAIアシスタント」ではありません。TrustLinkの組織の一員です。
- 社内の組織構成・メンバー・担当範囲はすべて把握しています（下記CLAUDE.mdに記載）。
- 「分かりません」「社内の連絡先を確認してください」などの汎用的回答は禁止です。
- 質問には組織図・振り分けルールに基づいて具体的なメンバー名と部門で回答してください。
- 話し相手は社長（ロキ）です。敬語は使いますが、堅すぎず親しみのあるトーンで。

## 回答スタイル（厳守）
- 必ず実データを確認し、具体的な数値・件数・日付で回答すること。
- 「確認してください」ではなく、自分で確認して結果を報告すること。
- TODOは件数・放置日数・期限を明示。メールは差出人・件名・日時を明示。予定は時間を明示。
- 曖昧な回答は禁止（「いくつか」「たくさん」→ 具体的な数値）。データがなければ「該当データなし」と明確に伝える。

## 書式ルール（厳守）
- **太字**で重要な数値・固有名詞を強調
- 絵文字を見出しに使い、セクションを視覚的に分離（📊📋💡🎯⚡🔴🟡🟢）
- ━━罫線でダッシュボードを囲む
- 箇条書きは階層化して情報密度を高める
- 1セクション3-5行以内。長文禁止。
- 提案は選択肢形式で提示（A案/B案/C案 → 推奨を明示）

## データファイルの場所
以下のファイルを直接読み書きしてデータを操作してください:
- TODO: {company_dir}/secretary/todos/active.md
- 夢・目標: {company_dir}/secretary/dreams/dreams.md
- 経費: {company_dir}/secretary/expenses/YYYY-MM.md
- Inbox: {company_dir}/secretary/inbox/YYYY-MM-DD.md

"""


def _build_system_prompt(department: str) -> str:
    """Build full system prompt with identity + department + datetime."""
    now = datetime.now(JST)
    weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    date_info = (
        f"\n\n## 現在の日時\n"
        f"{now.strftime('%Y-%m-%d')} ({weekdays[now.weekday()]}) "
        f"{now.strftime('%H:%M')} JST"
    )
    identity = IDENTITY_PREFIX.format(company_dir=COMPANY_DIR)
    return identity + load_department_prompt(department) + date_info


# ---------------------------------------------------------------------------
# CLI mode: use `claude -p` (subscription-based, no API cost)
# ---------------------------------------------------------------------------

def _process_cli(user_message: str, department: str, channel_id: str) -> str:
    """Process message using Claude Code CLI (`claude -p`)."""
    system_prompt = _build_system_prompt(department)

    # Build the full prompt with system context
    full_prompt = f"{system_prompt}\n\n---\n\nユーザーメッセージ:\n{user_message}"

    try:
        cmd = ["claude", "-p", full_prompt, "--output-format", "text", "--max-turns", "10"]
        if config.CLAUDE_MODEL_CLI:
            cmd.extend(["--model", config.CLAUDE_MODEL_CLI])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(COMPANY_DIR),
        )

        logger.info(f"CLI returncode={result.returncode} stdout_len={len(result.stdout)} stderr_len={len(result.stderr)}")
        if result.stderr:
            logger.warning(f"CLI stderr: {result.stderr[:500]}")
        if result.stdout.strip():
            return result.stdout.strip()
        else:
            error = result.stderr.strip() if result.stderr else f"returncode={result.returncode}, stdout empty"
            logger.error(f"CLI error: {error}")
            return f"⚠️ 処理中にエラーが発生しました。少し後にもう一度話しかけてください。"

    except subprocess.TimeoutExpired:
        logger.error("CLI timeout (120s)")
        return "⚠️ 処理がタイムアウトしました。もう少しシンプルに聞いてみてください。"
    except FileNotFoundError:
        logger.error("claude CLI not found, falling back to API")
        return _process_api(user_message, department, channel_id)
    except Exception as e:
        logger.error(f"CLI unexpected error: {e}")
        return f"⚠️ エラーが発生しました: {e}"


# ---------------------------------------------------------------------------
# API mode: use Anthropic API (pay-per-use fallback)
# ---------------------------------------------------------------------------

# Lazy-load API dependencies only when needed
_api_client = None
_api_tools = None
_api_tool_functions = None


def _ensure_api():
    """Lazy-load API client and tools."""
    global _api_client, _api_tools, _api_tool_functions

    if _api_client is not None:
        return

    from anthropic import Anthropic, APIStatusError
    from tools.todo import (
        get_today_todos, add_todo, complete_todo, update_todo,
        capture_inbox, get_pending_summary,
    )
    from tools.expense import record_expense, get_expense_summary
    from tools.dream import (
        add_dream, list_dreams, update_dream, complete_dream,
        get_pyramid_summary, get_future_timeline,
    )

    _api_client = Anthropic(api_key=config.ANTHROPIC_API_KEY)

    _api_tools = [
        {"name": "get_today_todos", "description": "今日のTODOリストを取得する",
         "input_schema": {"type": "object", "properties": {}, "required": []}},
        {"name": "add_todo", "description": "新しいTODOを追加する",
         "input_schema": {"type": "object", "properties": {
             "text": {"type": "string"}, "priority": {"type": "string", "enum": ["高", "通常", "低"]}
         }, "required": ["text"]}},
        {"name": "complete_todo", "description": "TODOを完了にする",
         "input_schema": {"type": "object", "properties": {
             "keyword": {"type": "string"}}, "required": ["keyword"]}},
        {"name": "update_todo", "description": "既存TODOのタスク名を更新する",
         "input_schema": {"type": "object", "properties": {
             "keyword": {"type": "string"}, "new_title": {"type": "string"}
         }, "required": ["keyword", "new_title"]}},
        {"name": "capture_inbox", "description": "Inboxにメモを記録する",
         "input_schema": {"type": "object", "properties": {
             "text": {"type": "string"}}, "required": ["text"]}},
        {"name": "get_pending_summary", "description": "未完了タスク・期限切れの概要を取得",
         "input_schema": {"type": "object", "properties": {}, "required": []}},
        {"name": "record_expense", "description": "経費を記録する",
         "input_schema": {"type": "object", "properties": {
             "description": {"type": "string"}, "amount": {"type": "integer"}, "category": {"type": "string"}
         }, "required": ["description", "amount"]}},
        {"name": "get_expense_summary", "description": "月間の経費サマリーを取得",
         "input_schema": {"type": "object", "properties": {
             "month": {"type": "string"}}, "required": []}},
        {"name": "add_dream", "description": "夢・やりたいことを追加する",
         "input_schema": {"type": "object", "properties": {
             "title": {"type": "string"}, "category": {"type": "string"}, "priority": {"type": "string"},
             "target_date": {"type": "string"}, "goals": {"type": "string"}
         }, "required": ["title"]}},
        {"name": "list_dreams", "description": "夢・やりたいことリストを取得する",
         "input_schema": {"type": "object", "properties": {
             "category": {"type": "string"}, "status": {"type": "string"}}, "required": []}},
        {"name": "update_dream", "description": "夢の進捗・予定日・優先度を更新する",
         "input_schema": {"type": "object", "properties": {
             "keyword": {"type": "string"}, "progress": {"type": "integer"},
             "target_date": {"type": "string"}, "priority": {"type": "string"}, "goals": {"type": "string"}
         }, "required": ["keyword"]}},
        {"name": "complete_dream", "description": "夢を達成済みにする",
         "input_schema": {"type": "object", "properties": {
             "keyword": {"type": "string"}}, "required": ["keyword"]}},
        {"name": "get_pyramid_summary", "description": "夢・人生ピラミッドの全体像を表示する",
         "input_schema": {"type": "object", "properties": {}, "required": []}},
        {"name": "get_future_timeline", "description": "未来年表を表示する",
         "input_schema": {"type": "object", "properties": {
             "year": {"type": "integer"}}, "required": []}},
    ]

    _api_tool_functions = {
        "get_today_todos": lambda **_: get_today_todos(),
        "add_todo": lambda **kw: add_todo(kw["text"], kw.get("priority", "通常")),
        "complete_todo": lambda **kw: complete_todo(kw["keyword"]),
        "update_todo": lambda **kw: update_todo(kw["keyword"], kw["new_title"]),
        "capture_inbox": lambda **kw: capture_inbox(kw["text"]),
        "get_pending_summary": lambda **_: json.dumps(get_pending_summary(), ensure_ascii=False),
        "record_expense": lambda **kw: record_expense(kw["description"], kw["amount"], kw.get("category", "その他")),
        "get_expense_summary": lambda **kw: json.dumps(get_expense_summary(kw.get("month", "")), ensure_ascii=False),
        "add_dream": lambda **kw: add_dream(kw["title"], kw.get("category", "未分類"), kw.get("priority", "B"), kw.get("target_date", ""), kw.get("goals", "")),
        "list_dreams": lambda **kw: list_dreams(kw.get("category", ""), kw.get("status", "active")),
        "update_dream": lambda **kw: update_dream(kw["keyword"], kw.get("progress"), kw.get("target_date"), kw.get("priority"), kw.get("goals")),
        "complete_dream": lambda **kw: complete_dream(kw["keyword"]),
        "get_pyramid_summary": lambda **_: get_pyramid_summary(),
        "get_future_timeline": lambda **kw: get_future_timeline(kw.get("year")),
    }


def _process_api(user_message: str, department: str, channel_id: str) -> str:
    """Process message using Anthropic API (fallback mode)."""
    from anthropic import APIStatusError

    _ensure_api()
    system_prompt = _build_system_prompt(department)

    history = conversations.get(channel_id, [])
    history.append({"role": "user", "content": user_message})
    if len(history) > MAX_HISTORY * 2:
        history = history[-MAX_HISTORY * 2:]
    conversations[channel_id] = history

    messages = list(history)
    max_iterations = 10
    text_parts = []

    for _ in range(max_iterations):
        response = None
        for attempt in range(3):
            try:
                response = _api_client.messages.create(
                    model=config.CLAUDE_MODEL,
                    max_tokens=2048,
                    system=system_prompt,
                    tools=_api_tools,
                    messages=messages,
                )
                break
            except APIStatusError as e:
                if e.status_code in (429, 529) and attempt < 2:
                    wait = 5 * (2 ** attempt)
                    logger.warning(f"API {e.status_code}, retrying in {wait}s (attempt {attempt + 1}/3)")
                    time.sleep(wait)
                else:
                    raise

        if response is None:
            result = "⚠️ APIが混み合っています。少し後にもう一度話しかけてください。"
            history.append({"role": "assistant", "content": result})
            return result

        text_parts = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(block)

        if not tool_calls:
            result = "\n".join(text_parts)
            history.append({"role": "assistant", "content": result})
            return result

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for tc in tool_calls:
            func = _api_tool_functions.get(tc.name)
            if func:
                try:
                    r = func(**tc.input)
                except Exception as e:
                    r = f"エラー: {e}"
            else:
                r = f"不明なツール: {tc.name}"
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": str(r),
            })
        messages.append({"role": "user", "content": tool_results})

    result = "\n".join(text_parts) if text_parts else "処理がタイムアウトしました。"
    history.append({"role": "assistant", "content": result})
    return result


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

conversations = {}
MAX_HISTORY = 20


def process_message(user_message: str, department: str, channel_id: str) -> str:
    """Process a message — dispatches to CLI or API based on ENGINE_MODE."""
    if ENGINE_MODE == "cli":
        return _process_cli(user_message, department, channel_id)
    else:
        return _process_api(user_message, department, channel_id)
