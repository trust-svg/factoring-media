"""TODO management tool — reads/writes .company/secretary/todos/"""

from datetime import date, timedelta
from pathlib import Path
from typing import Optional, List, Dict

from config import TODOS_DIR, INBOX_DIR


def _today_file() -> Path:
    return TODOS_DIR / f"{date.today().isoformat()}.md"


def _yesterday_file() -> Path:
    return TODOS_DIR / f"{(date.today() - timedelta(days=1)).isoformat()}.md"


def get_today_todos() -> str:
    f = _today_file()
    if f.exists():
        return f.read_text(encoding="utf-8")
    return f"今日（{date.today().isoformat()}）のTODOファイルはまだありません。"


def get_yesterday_carryover() -> List[str]:
    f = _yesterday_file()
    if not f.exists():
        return []
    lines = f.read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip().startswith("- [ ]")]


def add_todo(text: str, priority: str = "通常") -> str:
    f = _today_file()
    if not f.exists():
        weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        wd = weekdays[date.today().weekday()]
        content = f"""---
date: "{date.today().isoformat()}"
type: daily
---

# {date.today().isoformat()} ({wd})

## 最優先

## 通常

## 余裕があれば

## 完了

## メモ・振り返り
"""
        f.write_text(content, encoding="utf-8")

    lines = f.read_text(encoding="utf-8").splitlines()
    entry = f"- [ ] {text} | 優先度: {priority}"

    section_map = {"高": "## 最優先", "通常": "## 通常", "低": "## 余裕があれば"}
    target = section_map.get(priority, "## 通常")

    inserted = False
    result = []
    for i, line in enumerate(lines):
        result.append(line)
        if line.strip() == target and not inserted:
            result.append(entry)
            inserted = True

    if not inserted:
        result.append(entry)

    f.write_text("\n".join(result), encoding="utf-8")
    return f"追加しました: {text}（優先度: {priority}）"


def complete_todo(keyword: str) -> str:
    f = _today_file()
    if not f.exists():
        return "今日のTODOファイルがありません。"

    content = f.read_text(encoding="utf-8")
    lines = content.splitlines()
    found = False

    for i, line in enumerate(lines):
        if "- [ ]" in line and keyword in line:
            lines[i] = line.replace("- [ ]", "- [x]")
            if "完了:" not in lines[i]:
                lines[i] += f" | 完了: {date.today().isoformat()}"
            found = True
            break

    if found:
        f.write_text("\n".join(lines), encoding="utf-8")
        return f"「{keyword}」を完了にしました！"
    return f"「{keyword}」に一致するタスクが見つかりませんでした。"


def capture_inbox(text: str) -> str:
    from datetime import datetime
    today = date.today().isoformat()
    f = INBOX_DIR / f"{today}.md"

    if not f.exists():
        content = f"""---
date: "{today}"
type: inbox
---

# Inbox - {today}

## キャプチャ

"""
        f.write_text(content, encoding="utf-8")

    now = datetime.now().strftime("%H:%M")
    entry = f"- **{now}** | {text}\n"

    with open(f, "a", encoding="utf-8") as fh:
        fh.write(entry)

    return f"Inboxに記録しました: {text}"


def get_pending_summary() -> dict:
    today_todos = get_today_todos()
    yesterday_carry = get_yesterday_carryover()

    pending = [l for l in today_todos.splitlines() if "- [ ]" in l]
    completed = [l for l in today_todos.splitlines() if "- [x]" in l]
    high = [l for l in pending if "高" in l]
    deadline_today = [l for l in pending if f"期限: {date.today().isoformat()}" in l]

    return {
        "pending_count": len(pending),
        "completed_count": len(completed),
        "high_priority": high,
        "deadline_today": deadline_today,
        "yesterday_carryover": yesterday_carry,
    }
