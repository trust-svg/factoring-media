"""B-Manager — Telegram AI Secretary Server."""

import logging
from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI, Request, Response
from telegram import Bot, Update
from telegram.constants import ParseMode

import config
from secretary import (
    process_message, generate_morning_briefing, generate_evening_review,
    generate_weekly_review, generate_daily_report,
)
from scheduler import setup_scheduler, shutdown_scheduler, get_scheduler
from tools.reminder import init_reminder_system
from tools.voice import download_telegram_voice, transcribe_audio
from tools.todo import capture_inbox

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Telegram Bot setup
bot = Bot(token=config.TELEGRAM_BOT_TOKEN)

# Per-user conversation history (in-memory, simple)
conversations: Dict[int, list] = {}
MAX_HISTORY = 20


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_scheduler(send_message)
    # Initialize reminder system with scheduler
    sched = get_scheduler()
    if sched:
        init_reminder_system(sched, send_message)

    # Set webhook
    if config.RAILWAY_PUBLIC_DOMAIN:
        webhook_url = f"https://{config.RAILWAY_PUBLIC_DOMAIN}/webhook"
        await bot.set_webhook(
            url=webhook_url,
            secret_token=config.TELEGRAM_WEBHOOK_SECRET,
            drop_pending_updates=True,
        )
        logger.info(f"Webhook set: {webhook_url}")
    else:
        logger.warning("RAILWAY_PUBLIC_DOMAIN not set — webhook not registered")

    logger.info("B-Manager started (Telegram)")
    yield

    # Clean up (don't delete webhook — new instance will re-register)
    shutdown_scheduler()
    logger.info("B-Manager stopped")


app = FastAPI(title="B-Manager", lifespan=lifespan)


async def send_message(message: str, chat_id: int | str | None = None):
    """Send a message to the configured chat (broadcast replacement)."""
    target = chat_id or config.TELEGRAM_CHAT_ID
    if not target:
        logger.error("No chat_id configured for sending")
        return

    try:
        # Telegram message limit is 4096 chars
        chunks = [message[i : i + 4000] for i in range(0, len(message), 4000)]
        for chunk in chunks:
            await bot.send_message(chat_id=target, text=chunk)
        logger.info(f"Message sent: {message[:50]}...")
    except Exception as e:
        logger.error(f"Send message failed: {e}")


# Map Telegram /commands to natural language for the secretary
COMMAND_MAP = {
    "/briefing": "おはようございます。朝のブリーフィングをお願いします。",
    "/todo": "今日のTODOを見せて",
    "/schedule": "今日の予定を確認して",
    "/expense": "今月の経費サマリーを見せて",
    "/habit": "習慣チェックをお願い",
    "/help": "ヘルプ",
    "/start": "はじめまして！何ができるか教えて",
}


async def _handle_text_message(update: Update):
    """Handle text messages from Telegram."""
    chat_id = update.effective_chat.id
    user_text = update.message.text

    # Convert /commands to natural language
    cmd = user_text.split()[0] if user_text.startswith("/") else None
    if cmd and cmd in COMMAND_MAP:
        user_text = COMMAND_MAP[cmd]

    logger.info(f"Message from chat: {chat_id}")

    # Get or init conversation history
    history = conversations.get(chat_id, [])

    # Process with secretary
    try:
        reply = process_message(user_text, history.copy())
    except Exception as e:
        logger.error(f"Secretary error: {e}")
        reply = "申し訳ありません、処理中にエラーが発生しました。もう一度お試しください。"

    # Update history (keep last N messages)
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": reply})
    conversations[chat_id] = history[-MAX_HISTORY:]

    # Send reply (Telegram limit: 4096 chars)
    chunks = [reply[i : i + 4000] for i in range(0, len(reply), 4000)]
    for chunk in chunks:
        await bot.send_message(chat_id=chat_id, text=chunk)


async def _handle_voice_message(update: Update):
    """Handle voice messages — transcribe and save to inbox."""
    chat_id = update.effective_chat.id
    voice = update.message.voice or update.message.audio

    if not voice:
        await bot.send_message(chat_id=chat_id, text="音声ファイルを処理できませんでした。")
        return

    # Download voice from Telegram
    audio_bytes = await download_telegram_voice(bot, voice.file_id)

    if not audio_bytes:
        reply = "音声の取得に失敗しました。もう一度お試しください。"
    else:
        # Transcribe with Whisper
        transcription = await transcribe_audio(audio_bytes)

        if transcription.startswith("[音声メモ]"):
            reply = transcription
        else:
            # Save to inbox and confirm
            capture_inbox(f"🎤 音声メモ: {transcription}")
            reply = f"🎤 音声メモを記録しました\n\n「{transcription}」\n\nInboxに保存済みです。"

            # Also process as a message in case it's a command
            history = conversations.get(chat_id, [])
            try:
                ai_reply = process_message(
                    f"音声メッセージの文字起こし: {transcription}", history.copy()
                )
                reply = ai_reply
            except Exception:
                pass

    await bot.send_message(chat_id=chat_id, text=reply)


@app.post("/webhook")
async def webhook(request: Request):
    # Verify secret token
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if secret != config.TELEGRAM_WEBHOOK_SECRET:
        return Response(status_code=403)

    data = await request.json()
    update = Update.de_json(data, bot)

    if update.message:
        if update.message.text:
            await _handle_text_message(update)
        elif update.message.voice or update.message.audio:
            await _handle_voice_message(update)

    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "B-Manager", "platform": "telegram", "tools": 27}


@app.get("/briefing")
async def manual_briefing():
    msg = generate_morning_briefing()
    return {"briefing": msg}


@app.get("/review")
async def manual_review():
    msg = generate_evening_review()
    return {"review": msg}


@app.get("/weekly")
async def manual_weekly():
    msg = generate_weekly_review()
    return {"weekly": msg}


@app.get("/report")
async def manual_report():
    msg = generate_daily_report()
    return {"report": msg}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT)
