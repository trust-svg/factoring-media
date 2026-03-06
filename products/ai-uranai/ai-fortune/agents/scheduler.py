"""APScheduler オーケストレーター — 自動投稿・プッシュ・ナーチャリングを管理する"""
from __future__ import annotations

import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


async def _threads_configured() -> bool:
    """Threadsトークンが設定済みか確認（DB優先、env fallback）"""
    from database.crud import AsyncSessionLocal, get_setting
    async with AsyncSessionLocal() as session:
        token = await get_setting(session, "threads_access_token")
    if token:
        return True
    return bool(os.environ.get("THREADS_ACCESS_TOKEN") and os.environ.get("THREADS_USER_ID"))


async def _job_threads(slot: str) -> None:
    if not await _threads_configured():
        logger.info(f"Threads {slot}: APIキー未設定のためスキップ")
        return
    from agents.content_agent import run_content_agent
    try:
        logger.info(f"【スケジューラー】Threads {slot}投稿開始")
        result = await run_content_agent(slot)
        logger.info(f"Threads {slot}投稿完了: {result[:60]}...")
    except Exception as e:
        logger.error(f"Threads {slot}投稿エラー: {e}")


async def _job_refresh_threads_token() -> None:
    """Threadsの長期トークンをリフレッシュする（毎週実行）"""
    if not await _threads_configured():
        return
    from threads.api import ThreadsClient
    try:
        client = ThreadsClient()
        await client.refresh_long_lived_token()
        logger.info("【スケジューラー】Threadsトークンリフレッシュ完了")
    except Exception as e:
        logger.error(f"Threadsトークンリフレッシュエラー: {e}")


async def _job_check_replies() -> None:
    """Threadsコメントをチェックし、AI下書きを生成する"""
    if not await _threads_configured():
        return
    from agents.reply_agent import check_and_draft_replies
    try:
        logger.info("【スケジューラー】コメントチェック開始")
        count = await check_and_draft_replies()
        if count > 0:
            logger.info(f"コメントチェック完了: {count}件の新規下書き作成")
    except Exception as e:
        logger.error(f"コメントチェックエラー: {e}")


async def _job_collect_insights() -> None:
    """直近投稿のエンゲージメント指標を収集する"""
    if not await _threads_configured():
        return
    from database.crud import AsyncSessionLocal, get_recent_thread_post_ids, update_post_insights
    from threads.api import ThreadsClient
    try:
        logger.info("【スケジューラー】エンゲージメント収集開始")
        async with AsyncSessionLocal() as session:
            post_ids = await get_recent_thread_post_ids(session, days=7)
        client = ThreadsClient()
        count = 0
        for post_id in post_ids:
            try:
                metrics = await client.get_post_insights(post_id)
                async with AsyncSessionLocal() as session:
                    await update_post_insights(session, post_id, metrics)
                count += 1
            except Exception as e:
                logger.warning(f"Insights取得スキップ ({post_id}): {e}")
        if count > 0:
            logger.info(f"エンゲージメント収集完了: {count}件更新")
    except Exception as e:
        logger.error(f"エンゲージメント収集エラー: {e}")


async def _job_nurturing() -> None:
    from line_features.nurture import send_nurturing_messages
    try:
        logger.info("【スケジューラー】ナーチャリング送信開始")
        await send_nurturing_messages()
    except Exception as e:
        logger.error(f"ナーチャリングエラー: {e}")


def setup_scheduler() -> AsyncIOScheduler:
    """スケジューラーを設定して返す（start はライフスパン内で呼ぶ）"""
    tz = "Asia/Tokyo"
    scheduler = AsyncIOScheduler(timezone=tz)

    # 07:30 JST Threads 朝投稿（星座ランキング）
    scheduler.add_job(_job_threads, CronTrigger(hour=7, minute=30, timezone=tz), args=["morning"])
    # 08:00 JST ナーチャリングチェック（Day1/3/7）
    scheduler.add_job(_job_nurturing, CronTrigger(hour=8, minute=0, timezone=tz))
    # 13:00 JST Threads 昼投稿（タロットコンテンツ）
    scheduler.add_job(_job_threads, CronTrigger(hour=13, minute=0, timezone=tz), args=["afternoon"])
    # 16:00 JST Threads チャレンジ枠（実験投稿 — 毎回異なるフォーマット）
    scheduler.add_job(_job_threads, CronTrigger(hour=16, minute=0, timezone=tz), args=["challenge"])
    # 21:00 JST Threads 夜投稿（テーマローテーション + LINE誘導CTA）
    scheduler.add_job(_job_threads, CronTrigger(hour=21, minute=0, timezone=tz), args=["evening"])
    # 30分毎 Threadsコメントチェック → AI下書き生成
    scheduler.add_job(_job_check_replies, CronTrigger(minute="*/30", timezone=tz))
    # 10:00 JST エンゲージメント指標収集（毎日）
    scheduler.add_job(_job_collect_insights, CronTrigger(hour=10, minute=0, timezone=tz))
    # 毎週月曜 03:00 JST Threadsトークン自動リフレッシュ（60日有効 → 余裕を持って毎週更新）
    scheduler.add_job(_job_refresh_threads_token, CronTrigger(day_of_week="mon", hour=3, minute=0, timezone=tz))

    logger.info("スケジューラー設定完了")
    return scheduler
