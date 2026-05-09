"""TODO management tool — active.md file backend.

タスク状態（4値）:
  [UN] Unassigned  — 未着手
  [IN] In Progress — 着手中
  [BL] Blocked     — 待ち（ブロック理由を末尾に追記）
  [DN] Done        — 完了（完了日を末尾に追記）
"""

import re
import logging
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict

import config

logger = logging.getLogger(__name__)

ACTIVE_PATH = config.COMPANY_DIR / "secretary" / "todos" / "active.md"
INBOX_DIR = config.COMPANY_DIR / "secretary" / "inbox"
JST = timezone(timedelta(hours=9))

# 未完了タスク（UN/IN/BL）。スキップ欄はoptional。
TASK_PATTERN = re.compile(
    r"^- \[(UN|IN|BL)\] (.+?) \| 担当: (\S+) \| 期限: (\S+) \| 追加: (\d{4}-\d{2}-\d{2})(.*?)$",
    re.MULTILINE,
)

# 状態遷移用：未完了行先頭マッチ
INCOMPLETE_PREFIX = re.compile(r"^- \[(UN|IN|BL)\] ")

STATE_ICON = {"UN": "⚪", "IN": "🔵", "BL": "🟣"}


def _read_active() -> str:
    if ACTIVE_PATH.exists():
        return ACTIVE_PATH.read_text(encoding="utf-8")
    return ""


def _write_active(content: str):
    ACTIVE_PATH.write_text(content, encoding="utf-8")


def _line_is_incomplete(line: str) -> bool:
    return bool(INCOMPLETE_PREFIX.match(line.strip()))


def get_today_todos() -> str:
    """Get all incomplete tasks from active.md (UN/IN/BL)."""
    try:
        content = _read_active()
        if not content:
            return f"今日（{date.today().isoformat()}）のTODOはまだ登録されていません。"

        tasks = []
        for m in TASK_PATTERN.finditer(content):
            state = m.group(1)
            name = m.group(2)
            owner = m.group(3)
            deadline = m.group(4)
            added = m.group(5)
            extra = m.group(6) or ""
            skip_match = re.search(r"スキップ:\s*(\d+)", extra)
            skip = int(skip_match.group(1)) if skip_match else 0
            try:
                age = (date.today() - date.fromisoformat(added)).days
            except ValueError:
                age = 0

            priority_mark = ""
            if skip >= 3:
                priority_mark = " 🔴要判断"
            elif age >= 7:
                priority_mark = " 🟠放置"
            elif age >= 3:
                priority_mark = " 🟡"

            deadline_str = f" | 期限: {deadline}" if deadline != "なし" else ""
            icon = STATE_ICON.get(state, "⚪")
            tasks.append(
                f"- [{state}] {icon} {name} → {owner}{priority_mark}{deadline_str}"
            )

        if not tasks:
            return f"今日（{date.today().isoformat()}）のTODOはありません。素晴らしい！"

        lines = [f"# TODOリスト ({date.today().isoformat()})"]
        lines.extend(tasks)
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"get_today_todos error: {e}")
        return f"TODOの取得に失敗しました: {e}"


def add_todo(text: str, priority: str = "通常") -> str:
    """Add a new task (state=UN) to active.md."""
    try:
        content = _read_active()
        today = date.today().isoformat()

        if priority == "高":
            section = "## 高優先度"
        else:
            section = "## 通常"

        new_line = f"- [UN] {text} | 担当: アイ | 期限: なし | 追加: {today}"

        if section in content:
            content = content.replace(section, f"{section}\n{new_line}", 1)
        else:
            if "## ルーティン" in content:
                content = content.replace(
                    "## ルーティン", f"{section}\n{new_line}\n\n## ルーティン"
                )
            elif "## 完了" in content:
                content = content.replace(
                    "## 完了", f"{section}\n{new_line}\n\n## 完了"
                )
            else:
                content += f"\n{section}\n{new_line}\n"

        content = re.sub(
            r'updated: "\d{4}-\d{2}-\d{2}"',
            f'updated: "{today}"',
            content,
        )
        _write_active(content)
        return f"追加しました: {text}（優先度: {priority}）"
    except Exception as e:
        logger.error(f"add_todo error: {e}")
        return f"TODO追加に失敗しました: {e}"


def complete_todo(keyword: str) -> str:
    """Mark a task as completed (state=DN) by keyword match."""
    try:
        content = _read_active()
        today = date.today().isoformat()

        lines = content.split("\n")
        completed_task = None
        new_lines = []

        for line in lines:
            if keyword in line and _line_is_incomplete(line):
                m = re.match(r"^- \[(UN|IN|BL)\] (.+?) \|", line)
                task_name = m.group(2) if m else keyword
                completed_task = task_name
                continue
            new_lines.append(line)

        if not completed_task:
            return f"「{keyword}」に一致する未完了タスクが見つかりませんでした。"

        content = "\n".join(new_lines)

        completed_line = f"- [DN] {completed_task} | 完了: {today}"
        if "## 完了" in content:
            content = content.replace("## 完了", f"## 完了\n{completed_line}", 1)
        else:
            content += f"\n## 完了\n{completed_line}\n"

        content = re.sub(
            r'updated: "\d{4}-\d{2}-\d{2}"',
            f'updated: "{today}"',
            content,
        )
        _write_active(content)
        return f"「{completed_task}」を完了にしました！"
    except Exception as e:
        logger.error(f"complete_todo error: {e}")
        return f"TODO完了処理に失敗しました: {e}"


def drop_todo(keyword: str) -> str:
    """Remove a task entirely (drop/delete)."""
    try:
        content = _read_active()
        today = date.today().isoformat()

        lines = content.split("\n")
        dropped_task = None
        new_lines = []

        for line in lines:
            if keyword in line and _line_is_incomplete(line):
                m = re.match(r"^- \[(UN|IN|BL)\] (.+?) \|", line)
                dropped_task = m.group(2) if m else keyword
                continue
            new_lines.append(line)

        if not dropped_task:
            return f"「{keyword}」に一致するタスクが見つかりませんでした。"

        content = "\n".join(new_lines)
        content = re.sub(
            r'updated: "\d{4}-\d{2}-\d{2}"',
            f'updated: "{today}"',
            content,
        )
        _write_active(content)
        return f"「{dropped_task}」を削除しました。"
    except Exception as e:
        logger.error(f"drop_todo error: {e}")
        return f"TODO削除に失敗しました: {e}"


def defer_todo(keyword: str) -> str:
    """Reset skip count to 0 + 追加日を今日に更新（延期）。"""
    try:
        content = _read_active()
        today = date.today().isoformat()

        lines = content.split("\n")
        deferred_task = None

        for i, line in enumerate(lines):
            if keyword in line and _line_is_incomplete(line):
                m = re.match(r"^- \[(UN|IN|BL)\] (.+?) \|", line)
                deferred_task = m.group(2) if m else keyword
                if "スキップ:" in line:
                    lines[i] = re.sub(r"スキップ:\s*\d+", "スキップ: 0", line)
                else:
                    lines[i] = line  # スキップ欄なしならそのまま
                lines[i] = re.sub(
                    r"追加: \d{4}-\d{2}-\d{2}", f"追加: {today}", lines[i]
                )
                break

        if not deferred_task:
            return f"「{keyword}」に一致するタスクが見つかりませんでした。"

        content = "\n".join(lines)
        content = re.sub(
            r'updated: "\d{4}-\d{2}-\d{2}"',
            f'updated: "{today}"',
            content,
        )
        _write_active(content)
        return f"「{deferred_task}」を延期しました。"
    except Exception as e:
        logger.error(f"defer_todo error: {e}")
        return f"TODO延期に失敗しました: {e}"


def update_todo(keyword: str, new_title: str) -> str:
    """Update an existing task's title by keyword match."""
    try:
        content = _read_active()

        lines = content.split("\n")
        found = False
        for i, line in enumerate(lines):
            if keyword in line and _line_is_incomplete(line):
                old_match = re.match(r"^(- \[(?:UN|IN|BL)\] ).+?( \| 担当:.*)", line)
                if old_match:
                    lines[i] = f"{old_match.group(1)}{new_title}{old_match.group(2)}"
                    found = True
                    break

        if not found:
            return f"「{keyword}」に一致するタスクが見つかりませんでした。"

        content = "\n".join(lines)
        content = re.sub(
            r'updated: "\d{4}-\d{2}-\d{2}"',
            f'updated: "{date.today().isoformat()}"',
            content,
        )
        _write_active(content)
        return f"更新しました: 「{keyword}」→「{new_title}」"
    except Exception as e:
        logger.error(f"update_todo error: {e}")
        return f"TODO更新に失敗しました: {e}"


def set_state(keyword: str, new_state: str, block_reason: str = "") -> str:
    """Change task state (UN/IN/BL) by keyword match.

    BLにする場合は block_reason を末尾に追記する。
    """
    new_state = new_state.upper()
    if new_state not in ("UN", "IN", "BL"):
        return f"無効な状態: {new_state}（UN/IN/BL のいずれか）"

    try:
        content = _read_active()
        lines = content.split("\n")
        target = None

        for i, line in enumerate(lines):
            if keyword in line and _line_is_incomplete(line):
                m = re.match(r"^- \[(UN|IN|BL)\] (.+?) \|", line)
                target = m.group(2) if m else keyword
                lines[i] = re.sub(
                    r"^- \[(?:UN|IN|BL)\] ", f"- [{new_state}] ", lines[i]
                )
                # BL の場合、ブロック理由を末尾に追加（既存ブロック理由は上書き）
                if new_state == "BL":
                    lines[i] = re.sub(r"\s*\|\s*ブロック理由:.*$", "", lines[i])
                    reason_text = block_reason or "理由未記入"
                    lines[i] = f"{lines[i].rstrip()} | ブロック理由: {reason_text}"
                else:
                    # UN/IN に戻すときはブロック理由を削除
                    lines[i] = re.sub(r"\s*\|\s*ブロック理由:.*$", "", lines[i])
                break

        if not target:
            return f"「{keyword}」に一致する未完了タスクが見つかりませんでした。"

        content = "\n".join(lines)
        content = re.sub(
            r'updated: "\d{4}-\d{2}-\d{2}"',
            f'updated: "{date.today().isoformat()}"',
            content,
        )
        _write_active(content)
        suffix = (
            f"（理由: {block_reason}）" if new_state == "BL" and block_reason else ""
        )
        return f"「{target}」を {new_state} にしました{suffix}"
    except Exception as e:
        logger.error(f"set_state error: {e}")
        return f"状態変更に失敗しました: {e}"


def capture_inbox(text: str) -> str:
    """Capture a quick memo to inbox."""
    try:
        jst_now = datetime.now(JST)
        today = jst_now.strftime("%Y-%m-%d")
        now = jst_now.strftime("%H:%M")

        inbox_file = INBOX_DIR / f"{today}.md"

        if inbox_file.exists():
            content = inbox_file.read_text(encoding="utf-8")
            content += f"\n- **{now}** | {text}"
        else:
            content = (
                f'---\ndate: "{today}"\ntype: inbox\n---\n\n'
                f"# Inbox - {today}\n\n## キャプチャ\n\n"
                f"- **{now}** | {text}"
            )

        inbox_file.write_text(content, encoding="utf-8")
        return f"Inboxに記録しました: {text}"
    except Exception as e:
        logger.error(f"capture_inbox error: {e}")
        return f"Inbox記録に失敗しました: {e}"


def get_pending_summary() -> dict:
    """Get summary of pending tasks from active.md (UN/IN/BL)."""
    try:
        content = _read_active()
        tasks = []
        high_priority = []
        deadline_today = []
        today_str = date.today().isoformat()

        for m in TASK_PATTERN.finditer(content):
            name = m.group(2)
            deadline = m.group(4)
            tasks.append(name)

            pos = m.start()
            before = content[:pos]
            last_section = before.split("##")[-1] if "##" in before else ""
            if "緊急" in last_section or "高優先度" in last_section:
                high_priority.append(name)

            if deadline == today_str:
                deadline_today.append(name)

        return {
            "pending_count": len(tasks),
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
