"""AI占い LINE Bot — メインエントリーポイント"""

import asyncio
import base64
import hashlib
import hmac
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import FollowEvent, MessageEvent, TextMessageContent

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# LINE設定
line_config = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
line_handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])

# 非同期タスク実行用スレッドプール
_executor = ThreadPoolExecutor(max_workers=4)


def _run_async(coro):
    """同期 LINE ハンドラから非同期関数を実行するヘルパー"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=30)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from database.crud import init_db
    from agents.scheduler import setup_scheduler

    await init_db()
    logger.info("データベース初期化完了")

    scheduler = setup_scheduler()
    scheduler.start()
    logger.info("スケジューラー起動完了")

    yield

    scheduler.shutdown()
    logger.info("スケジューラー停止")


app = FastAPI(title="AI占いサロン Sion", lifespan=lifespan)

# STORES/管理エンドポイントを登録
from stores.webhook import router as stores_router  # noqa: E402
app.include_router(stores_router)


# ===================== プラン情報テキスト =====================

PLAN_INFO = (
    "🔮 AI占いサロン Sion — 鑑定メニュー\n\n"
    "【初回無料鑑定】\n"
    "・タロット・星座・数秘術から選べます\n"
    "・鑑定のエッセンスをお伝えします\n\n"
    "【本鑑定】¥3,500〜\n"
    "・恋愛・仕事・人生の転機を深く読み解きます\n"
    "・詳細レポートでお届け\n"
    "・STORES決済（クレカ・コンビニ払い対応）\n\n"
    "▶ sion-salon.stores.jp\n\n"
    "まずは初回無料鑑定からお試しください✨\n"
    "「タロット占いして」と送ってみてね🃏"
)

WELCOME_MESSAGE = (
    "✨ 友達追加ありがとうございます！\n\n"
    "AI占いサロン「Sion」へようこそ🌟\n\n"
    "初回限定で無料鑑定をお試しいただけます。\n"
    "「タロット占いして」と送ってみてください🃏\n\n"
    "下のメニューから占いの種類を選べます💫"
)


# ===================== Webhook エンドポイント =====================

@app.post("/webhook")
async def webhook(
    request: Request,
    x_line_signature: str = Header(alias="X-Line-Signature"),
) -> dict:
    body = await request.body()

    # 署名検証
    secret = os.environ["LINE_CHANNEL_SECRET"].encode("utf-8")
    sig = base64.b64encode(
        hmac.new(secret, body, hashlib.sha256).digest()
    ).decode()
    if not hmac.compare_digest(sig, x_line_signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    line_handler.handle(body.decode("utf-8"), x_line_signature)
    return {"status": "ok"}


# ===================== LINE イベントハンドラ =====================

@line_handler.add(FollowEvent)
def handle_follow(event: FollowEvent) -> None:
    """友達追加時: ウェルカムメッセージ送信 & ユーザー登録"""
    user_id = event.source.user_id

    async def _register():
        from database.crud import AsyncSessionLocal, get_or_create_user
        async with AsyncSessionLocal() as session:
            await get_or_create_user(session, user_id)

    try:
        _run_async(_register())
    except Exception as e:
        logger.warning(f"ユーザー登録失敗 {user_id}: {e}")

    _reply(event.reply_token, WELCOME_MESSAGE)


@line_handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event: MessageEvent) -> None:
    user_message = event.message.text.strip()
    user_id = event.source.user_id

    # アップグレードコード処理
    upper = user_message.upper()
    if upper.startswith("コード:") or upper.startswith("コード："):
        raw_code = user_message.split(":", 1)[-1].split("：", 1)[-1].strip()
        from stores.webhook import handle_upgrade_code
        reply = _run_async(handle_upgrade_code(user_id, raw_code))

    # プラン確認
    elif any(kw in user_message for kw in ("プラン", "料金", "値段", "課金")):
        reply = PLAN_INFO

    # 占いリクエスト → FortuneAgent
    else:
        from agents.fortune_agent import run_fortune_agent
        try:
            reply = _run_async(run_fortune_agent(user_id, user_message))
        except Exception as e:
            logger.error(f"FortuneAgent エラー {user_id}: {e}")
            reply = "申し訳ありません、只今占いが混み合っています🙏\nもう一度お試しください。"

    _reply(event.reply_token, reply)


# ===================== ヘルパー =====================

def _reply(reply_token: str, text: str) -> None:
    with ApiClient(line_config) as api_client:
        line_api = MessagingApi(api_client)
        line_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=text)],
            )
        )


# ===================== ヘルスチェック =====================

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "AI占いサロン Sion"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
