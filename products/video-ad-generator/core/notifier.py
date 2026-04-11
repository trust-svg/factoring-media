"""Telegram Bot 通知クライアント。"""
from __future__ import annotations
import logging
import httpx
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

_TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


async def notify(message: str) -> None:
    """Telegramにメッセージを送信する。失敗してもメイン処理をブロックしない。"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{_TELEGRAM_API}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            )
            if resp.status_code != 200:
                logger.warning(f"Telegram通知失敗: {resp.status_code} {resp.text[:100]}")
    except Exception as e:
        logger.warning(f"Telegram通知エラー（無視）: {e}")


async def notify_images_ready(count: int) -> None:
    await notify(f"🖼 <b>画像生成完了</b>\n{count}枚の画像が承認待ちです。\nUIで確認してください。")


async def notify_video_done(pattern: str, job_id: int) -> None:
    await notify(f"✅ <b>動画生成完了</b>\nパターン{pattern} (Job #{job_id}) が完成しました。")


async def notify_job_failed(job_id: int, error: str) -> None:
    await notify(f"❌ <b>生成失敗</b>\nJob #{job_id}: {error[:200]}")
