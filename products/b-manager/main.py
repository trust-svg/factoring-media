"""B-Manager — LINE AI Secretary Server."""

import logging
from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI, Request, HTTPException
from linebot.v3 import WebhookParser
from linebot.v3.messaging import (
    AsyncMessagingApi,
    AsyncApiClient,
    Configuration,
    ReplyMessageRequest,
    TextMessage,
    PushMessageRequest,
    BroadcastRequest,
)
from linebot.v3.webhooks import (
    MessageEvent, TextMessageContent, AudioMessageContent,
)
from linebot.v3.exceptions import InvalidSignatureError

import config
from secretary import (
    process_message, generate_morning_briefing, generate_evening_review,
    generate_weekly_review, generate_daily_report,
)
from scheduler import setup_scheduler, shutdown_scheduler, get_scheduler
from tools.reminder import init_reminder_system
from tools.voice import download_line_audio, transcribe_audio
from tools.todo import capture_inbox

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# LINE SDK setup
line_config = Configuration(access_token=config.LINE_CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(config.LINE_CHANNEL_SECRET)
async_api_client = AsyncApiClient(line_config)
api = AsyncMessagingApi(async_api_client)

# Per-user conversation history (in-memory, simple)
conversations: Dict[str, list] = {}
MAX_HISTORY = 20


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_scheduler(send_broadcast)
    # Initialize reminder system with scheduler
    sched = get_scheduler()
    if sched:
        init_reminder_system(sched, send_broadcast)
    logger.info("B-Manager started")
    yield
    shutdown_scheduler()
    logger.info("B-Manager stopped")


app = FastAPI(title="B-Manager", lifespan=lifespan)


async def send_broadcast(message: str):
    """Send a broadcast message to all LINE friends."""
    try:
        await api.broadcast(
            BroadcastRequest(messages=[TextMessage(text=message)])
        )
        logger.info(f"Broadcast sent: {message[:50]}...")
    except Exception as e:
        logger.error(f"Broadcast failed: {e}")


async def send_line_push(user_id: str, message: str):
    """Send a push message to a specific user."""
    try:
        await api.push_message(
            PushMessageRequest(
                to=user_id,
                messages=[TextMessage(text=message)],
            )
        )
    except Exception as e:
        logger.error(f"Push message failed: {e}")


async def _handle_text_message(event: MessageEvent):
    """Handle text messages from LINE."""
    user_id = event.source.user_id
    user_text = event.message.text
    logger.info(f"Message from user: {user_id}")

    # Get or init conversation history
    history = conversations.get(user_id, [])

    # Process with secretary
    try:
        reply = process_message(user_text, history.copy())
    except Exception as e:
        logger.error(f"Secretary error: {e}")
        reply = "申し訳ありません、処理中にエラーが発生しました。もう一度お試しください。"

    # Update history (keep last N messages)
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": reply})
    conversations[user_id] = history[-MAX_HISTORY:]

    # Split long messages (LINE limit: 5000 chars)
    chunks = [reply[i : i + 4500] for i in range(0, len(reply), 4500)]

    await api.reply_message(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage(text=chunk) for chunk in chunks[:5]],
        )
    )


async def _handle_audio_message(event: MessageEvent):
    """Handle audio messages — transcribe and save to inbox."""
    user_id = event.source.user_id
    message_id = event.message.id

    # Download audio from LINE
    audio_bytes = await download_line_audio(
        message_id, config.LINE_CHANNEL_ACCESS_TOKEN
    )

    if not audio_bytes:
        reply = "音声の取得に失敗しました。もう一度お試しください。"
    else:
        # Transcribe with Whisper
        transcription = await transcribe_audio(audio_bytes)

        if transcription.startswith("[音声メモ]"):
            # Error case
            reply = transcription
        else:
            # Save to inbox and confirm
            capture_inbox(f"🎤 音声メモ: {transcription}")
            reply = f"🎤 音声メモを記録しました\n\n「{transcription}」\n\nInboxに保存済みです。"

            # Also process as a message in case it's a command
            history = conversations.get(user_id, [])
            try:
                ai_reply = process_message(
                    f"音声メッセージの文字起こし: {transcription}", history.copy()
                )
                reply = ai_reply
            except Exception:
                pass

    await api.reply_message(
        ReplyMessageRequest(
            reply_token=event.reply_token,
            messages=[TextMessage(text=reply)],
        )
    )


@app.post("/webhook")
async def webhook(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = (await request.body()).decode("utf-8")

    try:
        events = parser.parse(body, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        if not isinstance(event, MessageEvent):
            continue

        if isinstance(event.message, TextMessageContent):
            await _handle_text_message(event)
        elif isinstance(event.message, AudioMessageContent):
            await _handle_audio_message(event)

    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "B-Manager", "tools": 27}


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
