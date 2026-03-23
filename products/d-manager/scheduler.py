"""Scheduled tasks — morning briefing, evening review, etc."""

import logging
import asyncio
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
from ai_engine import process_message

logger = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None
_send_fn = None

JST = timezone(timedelta(hours=9))


def _pick_daily_teaching() -> str:
    """Pick a daily teaching based on the date."""
    import random
    from datetime import date
    teachings = [
        "【7つの習慣】主体的であれ — 今日の出来事に対する反応は自分で選べる。",
        "【7つの習慣】目的を持って始める — 今日をどんな自分で終えたいか。",
        "【7つの習慣】重要事項を優先する — 緊急じゃないが重要なことに30分使おう。",
        "【ザ・パワー】良い感情こそが人生を動かすパワー。今何に愛を感じる？",
        "【ザ・パワー】感謝は最も強力なパワー。今あるものに心から感謝しよう。",
        "【鏡の法則】現実は自分の心を映す鏡。イラッとしたら自分の何が映っている？",
        "【夢ゾウ2】今日いつもと違う小さなチャレンジを1つやってみよう。",
    ]
    rng = random.Random(date.today().toordinal())
    return rng.choice(teachings)


async def morning_briefing():
    """Generate and send morning briefing."""
    logger.info("Running morning briefing...")
    teaching = _pick_daily_teaching()
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        process_message,
        f"おはようございます。朝のブリーフィングをお願いします。"
        f"カレンダー予定、未読メール、TODO（昨日の持ち越し含む）を確認して報告してください。"
        f"空き時間があれば活用提案もお願いします。"
        f"\n\n今日の教え: {teaching}",
        "secretary",
        "scheduler-briefing",
    )
    if _send_fn:
        await _send_fn("general", result)
    logger.info("Morning briefing sent")


async def evening_review():
    """Generate and send evening review."""
    logger.info("Running evening review...")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        process_message,
        "今日の振り返りをお願いします。TODOの完了率、未完了の持ち越し提案、明日の予定を確認してください。",
        "secretary",
        "scheduler-review",
    )
    if _send_fn:
        await _send_fn("general", result)
    logger.info("Evening review sent")


async def weekly_review():
    """Generate and send weekly review."""
    logger.info("Running weekly review...")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        process_message,
        "週次レビューをお願いします。今週のTODO完了状況、来週の予定プレビュー、経費サマリーをまとめてください。",
        "strategy",
        "scheduler-weekly",
    )
    if _send_fn:
        await _send_fn("strategy", result)
    logger.info("Weekly review sent")


def setup_scheduler(send_fn):
    """Setup APScheduler with scheduled jobs."""
    global _scheduler, _send_fn
    _send_fn = send_fn

    _scheduler = AsyncIOScheduler(timezone="Asia/Tokyo")

    _scheduler.add_job(
        morning_briefing,
        "cron",
        hour=config.MORNING_BRIEFING_HOUR,
        minute=config.MORNING_BRIEFING_MINUTE,
        name="朝のブリーフィング",
    )
    _scheduler.add_job(
        evening_review,
        "cron",
        hour=config.EVENING_REVIEW_HOUR,
        minute=config.EVENING_REVIEW_MINUTE,
        name="夕方の振り返り",
    )
    _scheduler.add_job(
        weekly_review,
        "cron",
        day_of_week="sun",
        hour=21,
        minute=0,
        name="週次レビュー",
    )

    _scheduler.start()
    logger.info(f"Scheduler started with {len(_scheduler.get_jobs())} jobs")
