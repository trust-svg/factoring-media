"""TODO management tool — Google Tasks API backend."""

import logging
from datetime import date, datetime, timezone
from typing import List, Dict, Optional

from googleapiclient.discovery import build
from tools.google_auth import get_credentials

logger = logging.getLogger(__name__)

_service = None
_tasklist_id = None

TASKLIST_NAME = "B-Manager"


def _get_service():
    global _service
    if not _service:
        creds = get_credentials()
        _service = build("tasks", "v1", credentials=creds)
    return _service


def _get_tasklist_id() -> str:
    """Get or create the B-Manager task list."""
    global _tasklist_id
    if _tasklist_id:
        return _tasklist_id

    service = _get_service()
    results = service.tasklists().list(maxResults=100).execute()
    for tl in results.get("items", []):
        if tl["title"] == TASKLIST_NAME:
            _tasklist_id = tl["id"]
            return _tasklist_id

    # Create if not exists
    new_list = service.tasklists().insert(body={"title": TASKLIST_NAME}).execute()
    _tasklist_id = new_list["id"]
    logger.info(f"Created task list: {TASKLIST_NAME}")
    return _tasklist_id


def get_today_todos() -> str:
    """Get all incomplete tasks from B-Manager task list."""
    try:
        service = _get_service()
        tl_id = _get_tasklist_id()
        results = service.tasks().list(
            tasklist=tl_id,
            showCompleted=False,
            showHidden=False,
            maxResults=50,
        ).execute()

        tasks = results.get("items", [])
        if not tasks:
            return f"今日（{date.today().isoformat()}）のTODOはまだ登録されていません。"

        lines = [f"# TODOリスト ({date.today().isoformat()})"]
        for t in tasks:
            title = t.get("title", "")
            notes = t.get("notes", "")
            due = t.get("due", "")
            priority_mark = ""
            if notes and "優先度: 高" in notes:
                priority_mark = " 🔴"
            elif notes and "優先度: 低" in notes:
                priority_mark = " 🔵"

            due_str = ""
            if due:
                due_str = f" | 期限: {due[:10]}"

            lines.append(f"- [ ] {title}{priority_mark}{due_str}")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"get_today_todos error: {e}")
        return f"TODOの取得に失敗しました: {e}"


def get_yesterday_carryover() -> List[str]:
    """Get incomplete tasks (all are carried over automatically in Google Tasks)."""
    return []


def add_todo(text: str, priority: str = "通常") -> str:
    """Add a new task to B-Manager task list."""
    try:
        service = _get_service()
        tl_id = _get_tasklist_id()

        body = {
            "title": text,
            "notes": f"優先度: {priority}",
        }

        # Set due date to today
        today_rfc = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00.000Z")
        body["due"] = today_rfc

        service.tasks().insert(tasklist=tl_id, body=body).execute()
        return f"追加しました: {text}（優先度: {priority}）"
    except Exception as e:
        logger.error(f"add_todo error: {e}")
        return f"TODO追加に失敗しました: {e}"


def complete_todo(keyword: str) -> str:
    """Mark a task as completed by keyword match."""
    try:
        service = _get_service()
        tl_id = _get_tasklist_id()
        results = service.tasks().list(
            tasklist=tl_id,
            showCompleted=False,
            maxResults=50,
        ).execute()

        for t in results.get("items", []):
            if keyword in t.get("title", ""):
                t["status"] = "completed"
                service.tasks().update(
                    tasklist=tl_id, task=t["id"], body=t
                ).execute()
                return f"「{keyword}」を完了にしました！"

        return f"「{keyword}」に一致するタスクが見つかりませんでした。"
    except Exception as e:
        logger.error(f"complete_todo error: {e}")
        return f"TODO完了処理に失敗しました: {e}"


def capture_inbox(text: str) -> str:
    """Capture a quick memo as a task with [Inbox] prefix."""
    try:
        service = _get_service()
        tl_id = _get_tasklist_id()

        now = datetime.now().strftime("%H:%M")
        body = {
            "title": f"[Inbox] {text}",
            "notes": f"キャプチャ: {now}",
        }
        service.tasks().insert(tasklist=tl_id, body=body).execute()
        return f"Inboxに記録しました: {text}"
    except Exception as e:
        logger.error(f"capture_inbox error: {e}")
        return f"Inbox記録に失敗しました: {e}"


def get_pending_summary() -> dict:
    """Get summary of pending tasks."""
    try:
        service = _get_service()
        tl_id = _get_tasklist_id()
        results = service.tasks().list(
            tasklist=tl_id,
            showCompleted=False,
            showHidden=False,
            maxResults=50,
        ).execute()

        tasks = results.get("items", [])
        today_str = date.today().isoformat()

        pending = []
        high_priority = []
        deadline_today = []

        for t in tasks:
            title = t.get("title", "")
            notes = t.get("notes", "")
            due = t.get("due", "")
            pending.append(title)

            if "優先度: 高" in notes:
                high_priority.append(title)
            if due and due[:10] == today_str:
                deadline_today.append(title)

        return {
            "pending_count": len(pending),
            "completed_count": 0,
            "high_priority": high_priority,
            "deadline_today": deadline_today,
            "yesterday_carryover": [],
        }
    except Exception as e:
        logger.error(f"get_pending_summary error: {e}")
        return {
            "pending_count": 0,
            "completed_count": 0,
            "high_priority": [],
            "deadline_today": [],
            "yesterday_carryover": [],
        }
