"""eBay Reply Assistant — Telegram Bot for Roki-style buyer responses."""

import logging
from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI, Request, Response
from telegram import Bot, Update

import config
from reply_engine import ReplySession, process

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=config.TELEGRAM_BOT_TOKEN)

# Per-chat reply sessions (in-memory)
sessions: Dict[int, ReplySession] = {}

HELP_TEXT = """\
📮 eBay返信アシスタント

使い方:
1. バイヤーメッセージを貼り付け → 翻訳+ドラフト生成
2. 修正指示を日本語で送信 → ドラフト修正
3.「OK」で確定 → コピペ用テキスト出力

コマンド:
/new — 新しいセッション開始
/help — このヘルプ\
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    if config.WEBHOOK_DOMAIN:
        webhook_url = f"https://{config.WEBHOOK_DOMAIN}/bm-webhook"
        await bot.set_webhook(
            url=webhook_url,
            secret_token=config.TELEGRAM_WEBHOOK_SECRET,
            drop_pending_updates=True,
        )
        logger.info(f"Webhook set: {webhook_url}")
    else:
        logger.warning("WEBHOOK_DOMAIN not set — webhook not registered")

    logger.info("eBay Reply Assistant started")
    yield
    logger.info("eBay Reply Assistant stopped")


app = FastAPI(title="eBay Reply Assistant", lifespan=lifespan)


async def _send(chat_id: int, text: str):
    """Send a message, chunking if needed for Telegram's 4096 char limit."""
    chunks = [text[i : i + 4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        await bot.send_message(chat_id=chat_id, text=chunk)


async def _handle_text_message(update: Update):
    """Handle incoming text messages."""
    chat_id = update.effective_chat.id
    user_text = update.message.text.strip()

    # Commands
    if user_text.lower() in ("/new", "/reset", "/clear"):
        sessions.pop(chat_id, None)
        await _send(chat_id, "🔄 新しいセッション開始。\nバイヤーメッセージを貼り付けてください。")
        return

    if user_text.lower() in ("/help", "/start"):
        await _send(chat_id, HELP_TEXT)
        return

    # Get or create session (auto-reset if finalized)
    session = sessions.get(chat_id, ReplySession())
    if session.finalized:
        session = ReplySession()

    logger.info(f"Processing message from chat {chat_id}")

    reply, session = process(user_text, session)
    sessions[chat_id] = session

    await _send(chat_id, reply)


@app.post("/bm-webhook")
async def webhook(request: Request):
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if secret != config.TELEGRAM_WEBHOOK_SECRET:
        return Response(status_code=403)

    data = await request.json()
    update = Update.de_json(data, bot)

    if update.message and update.message.text:
        await _handle_text_message(update)

    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "eBay Reply Assistant"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT)
