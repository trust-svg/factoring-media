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
from tools.expense import record_expense, get_expense_summary
from tools.dream import (
    add_dream, list_dreams, update_dream, complete_dream,
    get_pyramid_summary, get_future_timeline,
)

# Google OAuth tools — disabled until credentials are configured
try:
    from tools.calendar_tool import get_today_events, get_free_slots, create_event
    _calendar_available = True
except Exception:
    _calendar_available = False

try:
    from tools.gmail_tool import get_unread_emails, create_draft
    _gmail_available = True
except Exception:
    _gmail_available = False

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
    # --- Dream / Goal tools ---
    {
        "name": "add_dream",
        "description": "夢・やりたいことを追加する",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "夢のタイトル"},
                "category": {
                    "type": "string",
                    "enum": ["健康・美・知恵", "社会・仕事", "プライベート・家族", "教養・知識", "経済・モノ・お金", "心・精神", "未分類"],
                    "description": "人生ピラミッドのカテゴリ",
                },
                "priority": {"type": "string", "enum": ["A", "B", "C"], "description": "優先度（A=最高）"},
                "target_date": {"type": "string", "description": "実現予定日 (YYYY-MM-DD or YYYY)"},
                "goals": {"type": "string", "description": "具体的な目標・マイルストーン"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "list_dreams",
        "description": "夢・やりたいことリストを取得する",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "カテゴリでフィルタ（空=全て）"},
                "status": {"type": "string", "enum": ["active", "completed", "all"], "description": "状態フィルタ"},
            },
            "required": [],
        },
    },
    {
        "name": "update_dream",
        "description": "夢の進捗・予定日・優先度を更新する",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "夢を特定するキーワード"},
                "progress": {"type": "integer", "description": "進捗率 0-100%"},
                "target_date": {"type": "string", "description": "新しい実現予定日"},
                "priority": {"type": "string", "enum": ["A", "B", "C"]},
                "goals": {"type": "string", "description": "目標を更新"},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "complete_dream",
        "description": "夢を達成済みにする",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "夢を特定するキーワード"},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "get_pyramid_summary",
        "description": "夢・人生ピラミッドの全体像を表示する（カテゴリ別・レベル別）",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_future_timeline",
        "description": "未来年表を表示する（年齢別の夢マッピング）",
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "特定の年を指定（省略で全体表示）"},
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
    "get_today_events": lambda **_: json.dumps(get_today_events(), ensure_ascii=False) if _calendar_available else "Google Calendar未設定。OAuth設定が必要です。",
    "get_free_slots": lambda **kw: json.dumps(get_free_slots(kw.get("target_date")), ensure_ascii=False) if _calendar_available else "Google Calendar未設定。OAuth設定が必要です。",
    "create_event": lambda **kw: json.dumps(create_event(**kw), ensure_ascii=False) if _calendar_available else "Google Calendar未設定。OAuth設定が必要です。",
    "get_unread_emails": lambda **kw: json.dumps(get_unread_emails(kw.get("max_results", 5)), ensure_ascii=False) if _gmail_available else "Gmail未設定。OAuth設定が必要です。",
    "create_draft": lambda **kw: json.dumps(create_draft(**kw), ensure_ascii=False) if _gmail_available else "Gmail未設定。OAuth設定が必要です。",
    "record_expense": lambda **kw: record_expense(kw["description"], kw["amount"], kw.get("category", "その他")),
    "get_expense_summary": lambda **kw: json.dumps(get_expense_summary(kw.get("month", "")), ensure_ascii=False),
    # Dream tools
    "add_dream": lambda **kw: add_dream(kw["title"], kw.get("category", "未分類"), kw.get("priority", "B"), kw.get("target_date", ""), kw.get("goals", "")),
    "list_dreams": lambda **kw: list_dreams(kw.get("category", ""), kw.get("status", "active")),
    "update_dream": lambda **kw: update_dream(kw["keyword"], kw.get("progress"), kw.get("target_date"), kw.get("priority"), kw.get("goals")),
    "complete_dream": lambda **kw: complete_dream(kw["keyword"]),
    "get_pyramid_summary": lambda **_: get_pyramid_summary(),
    "get_future_timeline": lambda **kw: get_future_timeline(kw.get("year")),
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

## 回答スタイル（厳守）
- 必ずツールを使って実データを取得し、具体的な数値・件数・日付で回答すること。
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
- 関連する外部ツールへのリンクを積極的に含める

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
