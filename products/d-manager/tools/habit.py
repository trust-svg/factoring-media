"""Habit tracker — daily check-in for recurring habits."""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List

from config import SECRETARY_DIR

HABIT_DIR = SECRETARY_DIR / "habits"
HABIT_CONFIG = HABIT_DIR / "config.json"


def _ensure_dir():
    HABIT_DIR.mkdir(parents=True, exist_ok=True)


def _load_habits() -> List[str]:
    _ensure_dir()
    if HABIT_CONFIG.exists():
        return json.loads(HABIT_CONFIG.read_text(encoding="utf-8"))
    return []


def _today_file() -> Path:
    _ensure_dir()
    return HABIT_DIR / f"{date.today().isoformat()}.json"


def add_habit(name: str) -> str:
    """Register a new habit to track."""
    habits = _load_habits()
    if name in habits:
        return f"「{name}」は既に登録されています。"
    habits.append(name)
    HABIT_CONFIG.write_text(json.dumps(habits, ensure_ascii=False), encoding="utf-8")
    return f"習慣「{name}」を登録しました！毎日21時にチェックします。"


def remove_habit(name: str) -> str:
    """Remove a habit from tracking."""
    habits = _load_habits()
    if name not in habits:
        return f"「{name}」は登録されていません。"
    habits.remove(name)
    HABIT_CONFIG.write_text(json.dumps(habits, ensure_ascii=False), encoding="utf-8")
    return f"習慣「{name}」を削除しました。"


def check_habit(name: str, done: bool = True) -> str:
    """Mark a habit as done/not done for today."""
    f = _today_file()
    data = {}
    if f.exists():
        data = json.loads(f.read_text(encoding="utf-8"))

    data[name] = {
        "done": done,
        "checked_at": datetime.now().isoformat(),
    }
    f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    if done:
        return f"「{name}」達成！"
    return f"「{name}」は今日はスキップ。"


def get_habit_status() -> Dict:
    """Get today's habit check-in status."""
    habits = _load_habits()
    if not habits:
        return {"habits": [], "message": "登録されている習慣はありません。"}

    f = _today_file()
    checked = {}
    if f.exists():
        checked = json.loads(f.read_text(encoding="utf-8"))

    status = []
    done_count = 0
    for h in habits:
        is_done = checked.get(h, {}).get("done", False)
        if is_done:
            done_count += 1
        status.append({"name": h, "done": is_done})

    return {
        "habits": status,
        "total": len(habits),
        "done": done_count,
        "remaining": len(habits) - done_count,
    }


def get_weekly_streak() -> Dict:
    """Get weekly habit completion stats."""
    habits = _load_habits()
    from datetime import timedelta

    stats = {}
    for h in habits:
        streak = 0
        for i in range(7):
            d = date.today() - timedelta(days=i)
            f = HABIT_DIR / f"{d.isoformat()}.json"
            if f.exists():
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get(h, {}).get("done", False):
                    streak += 1
        stats[h] = {"days_done": streak, "total_days": 7}

    return stats
