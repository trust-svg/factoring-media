"""Reminder tool — schedule one-time reminders via APScheduler."""

import logging
from datetime import datetime, timedelta
from typing import Optional, Callable, Awaitable, List, Dict

logger = logging.getLogger(__name__)

# Will be set by main.py at startup
_scheduler = None
_broadcast_fn: Optional[Callable[[str], Awaitable[None]]] = None
_reminders: List[Dict] = []


def init_reminder_system(scheduler, broadcast_fn):
    """Initialize with scheduler and broadcast function."""
    global _scheduler, _broadcast_fn
    _scheduler = scheduler
    _broadcast_fn = broadcast_fn


def set_reminder(text: str, minutes: int = 0, hours: int = 0, time_str: str = "") -> str:
    """Set a one-time reminder.

    Args:
        text: What to remind about
        minutes: Minutes from now (e.g., 30)
        hours: Hours from now (e.g., 2)
        time_str: Specific time today (e.g., "15:00")
    """
    if not _scheduler:
        return "リマインダーシステムが初期化されていません。"

    now = datetime.now()

    if time_str:
        try:
            h, m = map(int, time_str.split(":"))
            target = now.replace(hour=h, minute=m, second=0)
            if target <= now:
                target += timedelta(days=1)
        except ValueError:
            return f"時間の形式が正しくありません: {time_str}（HH:MM形式で指定してください）"
    elif minutes or hours:
        target = now + timedelta(hours=hours, minutes=minutes)
    else:
        return "時間を指定してください（例: 30分後、2時間後、15:00）"

    job_id = f"reminder_{now.timestamp()}"

    async def _fire():
        if _broadcast_fn:
            await _broadcast_fn(f"⏰ リマインダー\n\n{text}")
        # Remove from tracking list
        _reminders[:] = [r for r in _reminders if r["id"] != job_id]

    _scheduler.add_job(
        _fire,
        "date",
        run_date=target,
        id=job_id,
        name=f"Reminder: {text[:30]}",
    )

    reminder_info = {
        "id": job_id,
        "text": text,
        "time": target.strftime("%H:%M"),
        "date": target.strftime("%Y-%m-%d"),
    }
    _reminders.append(reminder_info)

    return f"リマインダーをセットしました: {target.strftime('%H:%M')} に「{text}」"


def get_active_reminders() -> List[Dict]:
    """Get list of active (pending) reminders."""
    return _reminders.copy()


def cancel_reminder(keyword: str) -> str:
    """Cancel a reminder by keyword match."""
    if not _scheduler:
        return "リマインダーシステムが初期化されていません。"

    for r in _reminders:
        if keyword in r["text"]:
            try:
                _scheduler.remove_job(r["id"])
            except Exception:
                pass
            _reminders.remove(r)
            return f"リマインダー「{r['text']}」をキャンセルしました。"

    return f"「{keyword}」に一致するリマインダーが見つかりません。"
