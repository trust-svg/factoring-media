import json
import anthropic
from config import ANTHROPIC_API_KEY
import calendar_tool
import gmail_tool
import drive_tool

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Claude に渡す tool 定義
TOOLS = [
    {
        "name": "list_emails",
        "description": "Gmailの受信トレイから最新メールの一覧を取得する。",
        "input_schema": {
            "type": "object",
            "properties": {
                "max_results": {
                    "type": "integer",
                    "description": "取得するメール件数（デフォルト: 5）",
                },
                "query": {
                    "type": "string",
                    "description": "Gmailの検索クエリ（例: from:example@gmail.com）",
                },
            },
        },
    },
    {
        "name": "get_email",
        "description": "指定したIDのメール本文を取得する。",
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "メールID"},
            },
            "required": ["message_id"],
        },
    },
    {
        "name": "create_draft_reply",
        "description": "メールへの返信下書きを作成する。送信前にユーザー確認が必要。",
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "返信元メールID"},
                "body": {"type": "string", "description": "返信本文"},
            },
            "required": ["message_id", "body"],
        },
    },
    {
        "name": "send_draft",
        "description": "作成した下書きを送信する。必ずユーザー確認を得てから呼び出すこと。",
        "input_schema": {
            "type": "object",
            "properties": {
                "draft_id": {"type": "string", "description": "下書きID"},
            },
            "required": ["draft_id"],
        },
    },
    {
        "name": "list_calendar_events",
        "description": "Googleカレンダーの直近イベントを取得する。",
        "input_schema": {
            "type": "object",
            "properties": {
                "max_results": {
                    "type": "integer",
                    "description": "取得するイベント件数（デフォルト: 10）",
                },
            },
        },
    },
    {
        "name": "create_calendar_event",
        "description": "Googleカレンダーにイベントを登録する。必ずユーザー確認を得てから呼び出すこと。",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "イベントタイトル"},
                "start_datetime": {
                    "type": "string",
                    "description": "開始日時（ISO 8601形式、例: 2025-03-05T15:00:00+09:00）",
                },
                "end_datetime": {
                    "type": "string",
                    "description": "終了日時（ISO 8601形式）",
                },
                "location": {"type": "string", "description": "場所（省略可）"},
                "description": {"type": "string", "description": "説明（省略可）"},
            },
            "required": ["title", "start_datetime", "end_datetime"],
        },
    },
    {
        "name": "search_drive_files",
        "description": "Google Drive内のファイルをキーワードで検索する。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "検索キーワード"},
                "max_results": {
                    "type": "integer",
                    "description": "取得件数（デフォルト: 10）",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_drive_file",
        "description": "Google Driveの指定ファイルの内容を読み取る。",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "ファイルID"},
            },
            "required": ["file_id"],
        },
    },
    {
        "name": "update_drive_file",
        "description": "Google Driveのファイルを更新する。必ずユーザー確認を得てから呼び出すこと。",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "description": "ファイルID"},
                "new_content": {"type": "string", "description": "新しいファイル内容"},
            },
            "required": ["file_id", "new_content"],
        },
    },
]

# 破壊的操作（実行前にユーザー確認が必要）
DESTRUCTIVE_TOOLS = {"send_draft", "create_calendar_event", "update_drive_file"}

SYSTEM_PROMPT = """あなたはGoogleサービス（Gmail・Googleカレンダー・Googleドライブ）と連携するAIアシスタントです。
日本語で会話し、ユーザーの指示に従ってGoogleサービスを操作します。

【重要なルール】
- メール送信・カレンダー登録・ファイル更新などの操作は、必ず実行内容をユーザーに確認してから行うこと。
- 確認なしに破壊的操作を行ってはならない。
- ユーザーが「OK」「はい」「送って」などと言った場合のみ実行する。
- 操作前に「〇〇を実行します。よろしいですか？」と必ず確認する。
"""


def execute_tool(tool_name: str, tool_input: dict) -> str:
    """tool_use の呼び出しを実際の関数に振り分ける。"""
    try:
        if tool_name == "list_emails":
            result = gmail_tool.list_emails(**tool_input)
        elif tool_name == "get_email":
            result = gmail_tool.get_email(**tool_input)
        elif tool_name == "create_draft_reply":
            result = gmail_tool.create_draft_reply(**tool_input)
        elif tool_name == "send_draft":
            result = gmail_tool.send_draft(**tool_input)
        elif tool_name == "list_calendar_events":
            result = calendar_tool.list_calendar_events(**tool_input)
        elif tool_name == "create_calendar_event":
            result = calendar_tool.create_calendar_event(**tool_input)
        elif tool_name == "search_drive_files":
            result = drive_tool.search_drive_files(**tool_input)
        elif tool_name == "read_drive_file":
            result = drive_tool.read_drive_file(**tool_input)
        elif tool_name == "update_drive_file":
            result = drive_tool.update_drive_file(**tool_input)
        else:
            return f"未知のツール: {tool_name}"
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return f"エラーが発生しました: {e}"


def chat(messages: list[dict]) -> tuple[str, list[dict]]:
    """Claude にメッセージを送り、tool_use を処理して最終応答を返す。

    Returns:
        (応答テキスト, 更新されたメッセージリスト)
    """
    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # tool_use がなければ最終応答
        if response.stop_reason == "end_turn":
            text = "".join(
                block.text for block in response.content if hasattr(block, "text")
            )
            messages.append({"role": "assistant", "content": response.content})
            return text, messages

        # tool_use を処理
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []

        for block in response.content:
            if block.type != "tool_use":
                continue

            tool_name = block.name
            tool_input = block.input

            # 破壊的操作はユーザー確認（main.py 側で確認済みのものは通過）
            result = execute_tool(tool_name, tool_input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})
