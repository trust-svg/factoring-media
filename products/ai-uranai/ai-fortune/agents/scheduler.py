"""APScheduler オーケストレーター — 自動投稿・プッシュ・ナーチャリングを管理する"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


async def _job_threads_morning() -> None:
    from agents.content_agent import run_content_agent

    logger.info("【スケジューラー】Threads 朝投稿開始")
    result = await run_content_agent("morning")
    logger.info(f"Threads 朝投稿完了: {result[:60]}...")


async def _job_nurturing() -> None:
    from line_features.nurture import send_nurturing_messages

    logger.info("【スケジューラー】ナーチャリング送信開始")
    await send_nurturing_messages()


async def _job_threads_afternoon() -> None:
    from agents.content_agent import run_content_agent

    logger.info("【スケジューラー】Threads 昼投稿開始")
    result = await run_content_agent("afternoon")
    logger.info(f"Threads 昼投稿完了: {result[:60]}...")


async def _job_threads_evening() -> None:
    from agents.content_agent import run_content_agent

    logger.info("【スケジューラー】Threads 夜投稿開始")
    result = await run_content_agent("evening")
    logger.info(f"Threads 夜投稿完了: {result[:60]}...")


def setup_scheduler() -> AsyncIOScheduler:
    """スケジューラーを設定して返す（start はライフスパン内で呼ぶ）"""
    scheduler = AsyncIOScheduler(timezone="Asia/Tokyo")

    # 07:30 Threads 朝投稿（星座ランキング）
    scheduler.add_job(_job_threads_morning, CronTrigger(hour=7, minute=30))
    # 08:00 ナーチャリングチェック（Day1/3/7）
    scheduler.add_job(_job_nurturing, CronTrigger(hour=8, minute=0))
    # 13:00 Threads 昼投稿（タロットコンテンツ）
    scheduler.add_job(_job_threads_afternoon, CronTrigger(hour=13, minute=0))
    # 21:00 Threads 夜投稿（明日の運勢 + LINE誘導CTA）
    scheduler.add_job(_job_threads_evening, CronTrigger(hour=21, minute=0))

    logger.info("スケジューラー設定完了（4ジョブ登録）")
    return scheduler
