"""Proactive scheduler — morning briefing, evening review, weekly review, habits, free time."""

import logging
from typing import Callable, Awaitable, Optional

from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

JST = ZoneInfo("Asia/Tokyo")

import config
from secretary import (
    generate_morning_briefing, generate_evening_review,
    generate_weekly_review, generate_habit_check,
    generate_free_time_suggestion,
)
from tools.todo import get_pending_summary

logger = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None
_broadcast_fn: Optional[Callable[[str], Awaitable[None]]] = None


def get_scheduler() -> Optional[AsyncIOScheduler]:
    """Return the scheduler instance (used by reminder tool)."""
    return _scheduler


def setup_scheduler(broadcast_fn: Callable[[str], Awaitable[None]]):
    """Set up the proactive scheduler."""
    global _scheduler, _broadcast_fn
    _broadcast_fn = broadcast_fn

    _scheduler = AsyncIOScheduler(timezone="Asia/Tokyo")

    # Morning briefing (7:30)
    _scheduler.add_job(
        _morning_briefing_job,
        CronTrigger(hour=config.MORNING_BRIEFING_HOUR, minute=config.MORNING_BRIEFING_MINUTE, timezone=JST),
        id="morning_briefing",
        name="朝のブリーフィング",
    )

    # Evening review (21:00)
    _scheduler.add_job(
        _evening_review_job,
        CronTrigger(hour=config.EVENING_REVIEW_HOUR, minute=config.EVENING_REVIEW_MINUTE, timezone=JST),
        id="evening_review",
        name="夕方の振り返り",
    )

    # Deadline check (every 3 hours during work hours)
    _scheduler.add_job(
        _deadline_check_job,
        CronTrigger(hour="10,13,16,19", minute=0, timezone=JST),
        id="deadline_check",
        name="期限チェック",
    )

    # Weekly review (Sunday 21:00)
    _scheduler.add_job(
        _weekly_review_job,
        CronTrigger(day_of_week="sun", hour=21, minute=0, timezone=JST),
        id="weekly_review",
        name="週次レビュー",
    )

    # Habit check (daily 20:50, right before evening review)
    _scheduler.add_job(
        _habit_check_job,
        CronTrigger(hour=20, minute=50, timezone=JST),
        id="habit_check",
        name="習慣チェック",
    )

    # Free time suggestion (14:00)
    _scheduler.add_job(
        _free_time_job,
        CronTrigger(hour=14, minute=0, timezone=JST),
        id="free_time_check",
        name="空き時間提案",
    )

    _scheduler.start()
    logger.info("Scheduler started with 6 jobs")


def shutdown_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        logger.info("Scheduler stopped")


async def _morning_briefing_job():
    logger.info("Running morning briefing...")
    try:
        msg = generate_morning_briefing()
        if _broadcast_fn:
            await _broadcast_fn(msg)
        logger.info("Morning briefing sent")
    except Exception as e:
        logger.error(f"Morning briefing failed: {e}")


async def _evening_review_job():
    logger.info("Running evening review...")
    try:
        msg = generate_evening_review()
        if _broadcast_fn:
            await _broadcast_fn(msg)
        logger.info("Evening review sent")
    except Exception as e:
        logger.error(f"Evening review failed: {e}")


async def _deadline_check_job():
    logger.info("Running deadline check...")
    try:
        summary = get_pending_summary()
        urgent = summary.get("deadline_today", [])
        high = summary.get("high_priority", [])

        if not urgent and not high:
            return

        parts = ["⚠️ リマインド"]
        if urgent:
            parts.append(f"\n🔴 今日期限のタスク ({len(urgent)}件):")
            for t in urgent:
                parts.append(f"  {t.strip()}")
        if high:
            parts.append(f"\n🟠 高優先度の未完了 ({len(high)}件):")
            for t in high:
                parts.append(f"  {t.strip()}")

        msg = "\n".join(parts)
        if _broadcast_fn:
            await _broadcast_fn(msg)
        logger.info("Deadline reminder sent")
    except Exception as e:
        logger.error(f"Deadline check failed: {e}")


async def _weekly_review_job():
    logger.info("Running weekly review...")
    try:
        msg = generate_weekly_review()
        if _broadcast_fn:
            await _broadcast_fn(msg)
        logger.info("Weekly review sent")
    except Exception as e:
        logger.error(f"Weekly review failed: {e}")


async def _habit_check_job():
    logger.info("Running habit check...")
    try:
        msg = generate_habit_check()
        if msg and len(msg.strip()) > 10:
            if _broadcast_fn:
                await _broadcast_fn(msg)
            logger.info("Habit check sent")
    except Exception as e:
        logger.error(f"Habit check failed: {e}")


async def _free_time_job():
    logger.info("Running free time check...")
    try:
        msg = generate_free_time_suggestion()
        if msg and len(msg.strip()) > 10 and "空きがない" not in msg:
            if _broadcast_fn:
                await _broadcast_fn(msg)
            logger.info("Free time suggestion sent")
    except Exception as e:
        logger.error(f"Free time check failed: {e}")
