"""Secretary engine — Claude with tool_use for Discord integration."""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from anthropic import Anthropic

import config
from departments import load_department_prompt
from tools.todo import (
    get_today_todos, add_todo, complete_todo, update_todo,
    capture_inbox, get_pending_summary,
)
from tools.calendar_tool import get_today_events, get_free_slots, create_event
from tools.gmail_tool import get_unread_emails, create_draft
from tools.expense import record_expense, get_expense_summary

logger = logging.getLogger(__name__)
client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
JST = timezone(timedelta(hours=9))

TOOLS = [
    {
        "name": "get_today_todos",
        "description": "今日のTODOリストを取得する",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "add_todo",
        "description": "新しいTODOを追加する",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "タスク内容"},
                "priority": {"type": "string", "enum": ["高", "通常", "低"]},
            },
            "required": ["text"],
        },
    },
    {
        "name": "complete_todo",
        "description": "TODOを完了にする",
        "input_schema": {
            "type": "object",
            "properties": {"keyword": {"type": "string", "description": "タスクのキーワード"}},
            "required": ["keyword"],
        },
    },
    {
        "name": "update_todo",
        "description": "既存TODOのタスク名を更新する",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string"},
                "new_title": {"type": "string"},
            },
            "required": ["keyword", "new_title"],
        },
    },
    {
        "name": "capture_inbox",
        "description": "Inboxにメモを記録する",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "メモ内容"}},
            "required": ["text"],
        },
    },
    {
        "name": "get_pending_summary",
        "description": "未完了タスク・期限切れの概要を取得",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_today_events",
        "description": "今日のGoogleカレンダーの予定を取得",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_free_slots",
        "description": "空き時間を取得する",
        "input_schema": {
            "type": "object",
            "properties": {
                "target_date": {"type": "string", "description": "対象日 (YYYY-MM-DD)"},
            },
            "required": [],
        },
    },
    {
        "name": "create_event",
        "description": "Googleカレンダーに予定を登録",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["summary", "start_time", "end_time"],
        },
    },
    {
        "name": "get_unread_emails",
        "description": "未読メールを取得する",
        "input_schema": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer"},
            },
            "required": [],
        },
    },
    {
        "name": "create_draft",
        "description": "Gmailに返信ドラフトを作成する",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "record_expense",
        "description": "経費を記録する",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "amount": {"type": "integer"},
                "category": {"type": "string"},
            },
            "required": ["description", "amount"],
        },
    },
    {
        "name": "get_expense_summary",
        "description": "月間の経費サマリーを取得",
        "input_schema": {
            "type": "object",
            "properties": {
                "month": {"type": "string", "description": "YYYY-MM"},
            },
            "required": [],
        },
    },
]

TOOL_FUNCTIONS = {
    "get_today_todos": lambda **_: get_today_todos(),
    "add_todo": lambda **kw: add_todo(kw["text"], kw.get("priority", "通常")),
    "complete_todo": lambda **kw: complete_todo(kw["keyword"]),
    "update_todo": lambda **kw: update_todo(kw["keyword"], kw["new_title"]),
    "capture_inbox": lambda **kw: capture_inbox(kw["text"]),
    "get_pending_summary": lambda **_: json.dumps(get_pending_summary(), ensure_ascii=False),
    "get_today_events": lambda **_: json.dumps(get_today_events(), ensure_ascii=False),
    "get_free_slots": lambda **kw: json.dumps(get_free_slots(kw.get("target_date")), ensure_ascii=False),
    "create_event": lambda **kw: json.dumps(create_event(**kw), ensure_ascii=False),
    "get_unread_emails": lambda **kw: json.dumps(get_unread_emails(kw.get("max_results", 5)), ensure_ascii=False),
    "create_draft": lambda **kw: json.dumps(create_draft(**kw), ensure_ascii=False),
    "record_expense": lambda **kw: record_expense(kw["description"], kw["amount"], kw.get("category", "その他")),
    "get_expense_summary": lambda **kw: json.dumps(get_expense_summary(kw.get("month", "")), ensure_ascii=False),
}


# Per-channel conversation history
conversations: dict[str, list] = {}
MAX_HISTORY = 20


def process_message(user_message: str, department: str, channel_id: str) -> str:
    """Process a message with department-specific AI personality."""
    now = datetime.now(JST)
    weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    date_info = f"\n\n## 現在の日時\n{now.strftime('%Y-%m-%d')} ({weekdays[now.weekday()]}) {now.strftime('%H:%M')} JST"

    # 人格固定 + 組織コンテキスト強化
    identity_prefix = """## 最重要ルール
あなたはTrustLinkのAI社員です。以下のCLAUDE.mdで定義された人格として振る舞ってください。
- あなたは「外部のAIアシスタント」ではありません。TrustLinkの組織の一員です。
- 社内の組織構成・メンバー・担当範囲はすべて把握しています（下記CLAUDE.mdに記載）。
- 「分かりません」「社内の連絡先を確認してください」などの汎用的回答は禁止です。
- 質問には組織図・振り分けルールに基づいて具体的なメンバー名と部門で回答してください。
- 話し相手は社長（ロキ）です。敬語は使いますが、堅すぎず親しみのあるトーンで。

"""

    system_prompt = identity_prefix + load_department_prompt(department) + date_info

    # Get or create conversation history for this channel
    history = conversations.get(channel_id, [])
    history.append({"role": "user", "content": user_message})

    # Trim history
    if len(history) > MAX_HISTORY * 2:
        history = history[-MAX_HISTORY * 2:]
    conversations[channel_id] = history

    # Agentic loop
    messages = list(history)
    max_iterations = 10
    for _ in range(max_iterations):
        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=2048,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )

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
            func = TOOL_FUNCTIONS.get(tc.name)
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
