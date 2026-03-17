"""Secretary engine — Claude with tool_use for Telegram integration."""

import json
from typing import Optional
from anthropic import Anthropic

import config
from tools.todo import (
    get_today_todos, add_todo, complete_todo,
    capture_inbox, get_pending_summary, get_yesterday_carryover,
)
from tools.calendar_tool import get_today_events, get_free_slots, create_event
from tools.gmail_tool import get_unread_emails, create_draft
from tools.expense import record_expense, get_expense_summary
from tools.habit import add_habit, remove_habit, check_habit, get_habit_status, get_weekly_streak
from tools.reminder import set_reminder, get_active_reminders, cancel_reminder
from tools.ebay_sales import get_ebay_sales_summary, get_ebay_active_listings, get_ebay_messages
from tools.notion_tool import get_notion_tasks, update_notion_task, add_notion_task

client = Anthropic(api_key=config.ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """あなたは専属のAI秘書「Bマネージャー」です。

## キャラクター
- 丁寧だが堅すぎない。親しみやすい口調。
- 主体的に提案する。「ついでにこれもやっておきましょうか？」
- 簡潔に要点を伝える（Telegramなので読みやすく）。
- 絵文字は適度に使う（📅📧📋✅🔴🟡💡⏰💰🏋️）。

## できること（全21機能）

### 基本機能
1. TODO管理（追加・完了・確認）
2. カレンダー（予定確認・登録・空き時間）
3. メール（未読確認・要約・返信ドラフト）
4. メモ・クイックキャプチャ（Inbox）
5. 朝のブリーフィング
6. 振り返り

### 拡張機能
7. 今日のプランニング — カレンダー+TODO+メールから最適な時間割を提案
8. 週次レビュー — 1週間の振り返りと来週の準備
9. メールトリアージ — 未読メールを「要返信/参考/無視」に自動分類
10. リマインダー — 「○分後にリマインドして」
11. eBay売上日報 — eBayの売上・在庫・メッセージ確認
12. 経費記録 — 「コンビニ 580円」で記録、月次サマリー
13. Notion連携 — Notionのタスク取得・追加・更新
14. 習慣トラッカー — 毎日の習慣を記録・ストリーク確認
15. AI日報生成 — TODO完了状況+カレンダーから自動日報
16. 空き時間提案 — 空き時間があれば有効活用を提案

## ルール
- ユーザーの発言を分析し、適切なツールを使う
- 複数ツールが必要な場合は順番に実行
- 結果はTelegramで読みやすい形式にフォーマット
- 「おはよう」「ブリーフィング」→ 朝のブリーフィングを実行
- 「振り返り」「今日どうだった」→ 夕方の振り返りを実行
- 「今日なにする？」「プランニング」→ 今日のプランを提案
- 「ヘルプ」「メニュー」「何ができる？」→ 機能一覧を表示（show_helpツールを使う）
- 「○○リマインドして」→ リマインダー設定
- 「経費」「○○ ○○円」→ 経費記録
- 「習慣」「ハビット」→ 習慣トラッカー
- ツールが空の結果（[]や空文字）を返した場合、それはエラーではなく「該当なし」を意味する
  - カレンダーが空 → 「今日の予定はありません」
  - メールが空 → 「未読メールはありません」
  - TODOが空 → 「今日のTODOはまだ登録されていません」
- ebay/notion関連でerrorが含まれる場合は「現在接続できません」と伝える（エラー詳細は省略）
"""

HELP_TEXT = """📱 B-Manager できること一覧

📋 TODO管理
  「タスク追加: ○○」「○○完了」「今日のタスク」

📅 カレンダー
  「今日の予定」「空き時間」「予定を入れて」

📧 メール
  「メール確認」「メールまとめて」「返信の下書き」

💡 プランニング
  「今日なにする？」「プランニング」

📝 メモ
  「メモ: ○○」

⏰ リマインダー
  「30分後にリマインド」「15:00に○○」

💰 経費記録
  「コンビニ 580円」「今月の経費」

🏋️ 習慣トラッカー
  「習慣追加: 運動」「運動した」「習慣チェック」

📊 eBay売上
  「eBay売上」「eBayメッセージ」

📓 Notion
  「Notionタスク」「Notion追加: ○○」

📈 レポート
  「日報」「週次レビュー」「振り返り」

🔔 自動通知
  朝7:30 ブリーフィング / 21:00 振り返り
  日曜21:00 週次レビュー / 21:00 習慣チェック"""

TOOLS = [
    # === Basic TODO ===
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
                "priority": {"type": "string", "enum": ["高", "通常", "低"], "description": "優先度"},
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
        "description": "未完了タスク・期限切れ・持ち越しの概要を取得",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    # === Calendar ===
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
                "target_date": {"type": "string", "description": "対象日 (YYYY-MM-DD)。省略で今日。"},
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
                "summary": {"type": "string", "description": "予定のタイトル"},
                "start_time": {"type": "string", "description": "開始日時 (ISO 8601)"},
                "end_time": {"type": "string", "description": "終了日時 (ISO 8601)"},
                "description": {"type": "string", "description": "説明（任意）"},
            },
            "required": ["summary", "start_time", "end_time"],
        },
    },
    # === Gmail ===
    {
        "name": "get_unread_emails",
        "description": "未読メールを取得する",
        "input_schema": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "description": "取得件数（デフォルト5）"},
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
                "to": {"type": "string", "description": "宛先メールアドレス"},
                "subject": {"type": "string", "description": "件名"},
                "body": {"type": "string", "description": "本文"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    # === Expense ===
    {
        "name": "record_expense",
        "description": "経費を記録する（例: コンビニ 580円）",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "経費の内容"},
                "amount": {"type": "integer", "description": "金額（円）"},
                "category": {
                    "type": "string",
                    "description": "カテゴリ",
                    "enum": ["交通費", "食費", "消耗品", "通信費", "仕入", "外注費", "その他"],
                },
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
                "month": {"type": "string", "description": "対象月 (YYYY-MM)。省略で今月。"},
            },
            "required": [],
        },
    },
    # === Habit Tracker ===
    {
        "name": "add_habit",
        "description": "追跡する習慣を新規登録する",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "習慣名（例: 運動、英語学習）"}},
            "required": ["name"],
        },
    },
    {
        "name": "check_habit",
        "description": "今日の習慣達成を記録する",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "習慣名"},
                "done": {"type": "boolean", "description": "達成したか（デフォルトtrue）"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_habit_status",
        "description": "今日の習慣チェック状況を取得",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_weekly_streak",
        "description": "週間の習慣達成ストリークを取得",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "remove_habit",
        "description": "習慣の追跡をやめる",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "習慣名"}},
            "required": ["name"],
        },
    },
    # === Reminder ===
    {
        "name": "set_reminder",
        "description": "リマインダーを設定する",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "リマインドする内容"},
                "minutes": {"type": "integer", "description": "○分後（例: 30）"},
                "hours": {"type": "integer", "description": "○時間後（例: 2）"},
                "time_str": {"type": "string", "description": "具体的な時刻（例: 15:00）"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "get_active_reminders",
        "description": "設定済みのリマインダー一覧を取得",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "cancel_reminder",
        "description": "リマインダーをキャンセルする",
        "input_schema": {
            "type": "object",
            "properties": {"keyword": {"type": "string", "description": "キャンセルするリマインダーのキーワード"}},
            "required": ["keyword"],
        },
    },
    # === eBay ===
    {
        "name": "get_ebay_sales_summary",
        "description": "eBayの今日の売上サマリーを取得",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_ebay_active_listings",
        "description": "eBayのアクティブ出品数・ダッシュボード情報を取得",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_ebay_messages",
        "description": "eBayの未読メッセージを取得",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    # === Notion ===
    {
        "name": "get_notion_tasks",
        "description": "Notionデータベースからタスクを取得",
        "input_schema": {
            "type": "object",
            "properties": {
                "status_filter": {"type": "string", "description": "ステータスフィルタ（例: 未着手, 進行中, 完了）"},
            },
            "required": [],
        },
    },
    {
        "name": "add_notion_task",
        "description": "Notionにタスクを追加",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "タスク名"},
                "status": {"type": "string", "description": "ステータス（デフォルト: 未着手）"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "update_notion_task",
        "description": "Notionタスクのステータスを更新",
        "input_schema": {
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "ページID"},
                "status": {"type": "string", "description": "新しいステータス"},
            },
            "required": ["page_id", "status"],
        },
    },
    # === Help ===
    {
        "name": "show_help",
        "description": "B-Managerの機能一覧を表示する",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

TOOL_FUNCTIONS = {
    # Basic
    "get_today_todos": lambda **_: get_today_todos(),
    "add_todo": lambda **kw: add_todo(kw["text"], kw.get("priority", "通常")),
    "complete_todo": lambda **kw: complete_todo(kw["keyword"]),
    "capture_inbox": lambda **kw: capture_inbox(kw["text"]),
    "get_pending_summary": lambda **_: json.dumps(get_pending_summary(), ensure_ascii=False),
    # Calendar
    "get_today_events": lambda **_: json.dumps(get_today_events(), ensure_ascii=False),
    "get_free_slots": lambda **kw: json.dumps(get_free_slots(kw.get("target_date")), ensure_ascii=False),
    "create_event": lambda **kw: json.dumps(create_event(**kw), ensure_ascii=False),
    # Gmail
    "get_unread_emails": lambda **kw: json.dumps(get_unread_emails(kw.get("max_results", 5)), ensure_ascii=False),
    "create_draft": lambda **kw: json.dumps(create_draft(**kw), ensure_ascii=False),
    # Expense
    "record_expense": lambda **kw: record_expense(kw["description"], kw["amount"], kw.get("category", "その他")),
    "get_expense_summary": lambda **kw: json.dumps(get_expense_summary(kw.get("month", "")), ensure_ascii=False),
    # Habit
    "add_habit": lambda **kw: add_habit(kw["name"]),
    "check_habit": lambda **kw: check_habit(kw["name"], kw.get("done", True)),
    "get_habit_status": lambda **_: json.dumps(get_habit_status(), ensure_ascii=False),
    "get_weekly_streak": lambda **_: json.dumps(get_weekly_streak(), ensure_ascii=False),
    "remove_habit": lambda **kw: remove_habit(kw["name"]),
    # Reminder
    "set_reminder": lambda **kw: set_reminder(kw["text"], kw.get("minutes", 0), kw.get("hours", 0), kw.get("time_str", "")),
    "get_active_reminders": lambda **_: json.dumps(get_active_reminders(), ensure_ascii=False),
    "cancel_reminder": lambda **kw: cancel_reminder(kw["keyword"]),
    # eBay
    "get_ebay_sales_summary": lambda **_: json.dumps(get_ebay_sales_summary(), ensure_ascii=False),
    "get_ebay_active_listings": lambda **_: json.dumps(get_ebay_active_listings(), ensure_ascii=False),
    "get_ebay_messages": lambda **_: json.dumps(get_ebay_messages(), ensure_ascii=False),
    # Notion
    "get_notion_tasks": lambda **kw: json.dumps(get_notion_tasks(kw.get("status_filter", "")), ensure_ascii=False),
    "add_notion_task": lambda **kw: json.dumps(add_notion_task(kw["title"], kw.get("status", "未着手")), ensure_ascii=False),
    "update_notion_task": lambda **kw: json.dumps(update_notion_task(kw["page_id"], kw["status"]), ensure_ascii=False),
    # Help
    "show_help": lambda **_: HELP_TEXT,
}


def _load_rules() -> str:
    if config.RULES_FILE.exists():
        return config.RULES_FILE.read_text(encoding="utf-8")
    return ""


def process_message(user_message: str, conversation_history: Optional[list] = None) -> str:
    """Process a user message and return the secretary's response."""
    rules = _load_rules()
    system = SYSTEM_PROMPT
    if rules:
        system += f"\n\n## 学習済みルール\n{rules}"

    messages = conversation_history or []
    messages.append({"role": "user", "content": user_message})

    # Agentic loop
    max_iterations = 10
    for _ in range(max_iterations):
        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=2048,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        # Collect text and tool_use blocks
        text_parts = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(block)

        if not tool_calls:
            return "\n".join(text_parts)

        # Execute tool calls and build tool results
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for tc in tool_calls:
            func = TOOL_FUNCTIONS.get(tc.name)
            if func:
                try:
                    result = func(**tc.input)
                except Exception as e:
                    result = f"エラー: {e}"
            else:
                result = f"不明なツール: {tc.name}"

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": str(result),
            })

        messages.append({"role": "user", "content": tool_results})

    return "\n".join(text_parts) if text_parts else "処理がタイムアウトしました。"


def generate_morning_briefing() -> str:
    """Generate morning briefing message."""
    return process_message(
        "おはようございます。朝のブリーフィングをお願いします。"
        "今日のカレンダー予定、未読メール、TODO（昨日の持ち越し含む）を確認して報告してください。"
        "空き時間があれば、どう活用するか提案もしてください。"
    )


def generate_evening_review() -> str:
    """Generate evening review message."""
    return process_message(
        "今日の振り返りをお願いします。"
        "TODOの完了率、未完了タスクの持ち越し提案、習慣の達成状況、明日の予定を確認してください。"
    )


def generate_weekly_review() -> str:
    """Generate weekly review message."""
    return process_message(
        "週次レビューをお願いします。"
        "今週のTODO完了状況、習慣の週間ストリーク、来週の予定プレビュー、"
        "経費サマリーを確認してまとめてください。来週に向けた提案もお願いします。"
    )


def generate_daily_report() -> str:
    """Generate AI daily report."""
    return process_message(
        "今日のAI日報を生成してください。"
        "カレンダーの予定実績、TODOの完了状況、メール対応状況を元に、"
        "簡潔な業務日報形式でまとめてください。"
    )


def generate_habit_check() -> str:
    """Generate habit check-in prompt."""
    return process_message(
        "習慣チェックの時間です。今日の習慣の達成状況を確認して、"
        "まだチェックしていないものがあれば聞いてください。"
    )


def generate_free_time_suggestion() -> str:
    """Check for free time and suggest activities."""
    return process_message(
        "空き時間チェックです。今日の残りの空き時間を確認して、"
        "2時間以上の空きがあればおすすめの活用方法を提案してください。"
        "空きがなければ何も返さないでください。"
    )
