"""ZINQ Suite — LINE Bot メインエントリーポイント

マッチングアプリ攻略Bot Suite。
MVP: プロフィール写真診断のみ。
"""
from __future__ import annotations

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
    MessagingApiBlob,
    PushMessageRequest,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import (
    FollowEvent,
    ImageMessageContent,
    MessageEvent,
    TextMessageContent,
)

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

line_config = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
line_handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])

_executor = ThreadPoolExecutor(max_workers=4)
_main_loop: asyncio.AbstractEventLoop | None = None


def _run_async(coro):
    loop = _main_loop
    if loop is not None and loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=120)
    return asyncio.run(coro)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _main_loop
    _main_loop = asyncio.get_event_loop()
    from database.crud import init_db
    await init_db()
    logger.info("DB初期化完了")
    yield


app = FastAPI(title="ZINQ Suite", lifespan=lifespan)

from payment.square_webhook import router as payment_router  # noqa: E402
app.include_router(payment_router)


# ===================== 定数 =====================

WELCOME_MESSAGE = (
    "👋 ZINQ Suite へようこそ！\n\n"
    "マッチングアプリ攻略をAIがサポートします。\n\n"
    "まずは無料で「プロフィール写真診断」を試してみてください📸\n"
    "写真を1枚送ってください👇\n\n"
    "⚠️ 写真は診断後すぐに削除します。\n"
    "スコアデータのみ記録します（月次レポート用）。"
)

PLAN_INFO = (
    "💳 ZINQ Suite — プラン\n\n"
    "【Free】¥0\n"
    "・プロフィール写真診断 1回\n\n"
    "【Standard】¥980/月\n"
    "・全Bot月10回ずつ利用可能\n\n"
    "【Premium】¥2,480/月\n"
    "・全Bot使い放題\n"
    "・月次総合診断レポート付き\n\n"
    "▶ プランを変更する: {checkout_url}"
)


# ===================== Webhook =====================

@app.post("/webhook")
async def webhook(
    request: Request,
    x_line_signature: str = Header(alias="X-Line-Signature"),
) -> dict:
    global _main_loop
    if _main_loop is None:
        _main_loop = asyncio.get_event_loop()

    body = await request.body()
    secret = os.environ["LINE_CHANNEL_SECRET"].encode("utf-8")
    sig = base64.b64encode(hmac.new(secret, body, hashlib.sha256).digest()).decode()
    if not hmac.compare_digest(sig, x_line_signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    body_str = body.decode("utf-8")
    await asyncio.get_event_loop().run_in_executor(
        _executor, line_handler.handle, body_str, x_line_signature
    )
    return {"status": "ok"}


# ===================== イベントハンドラ =====================

@line_handler.add(FollowEvent)
def handle_follow(event: FollowEvent) -> None:
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
def handle_text(event: MessageEvent) -> None:
    text = event.message.text.strip()
    user_id = event.source.user_id

    if any(kw in text for kw in ("プラン", "料金", "値段", "プレミアム", "スタンダード")):
        from payment.square_webhook import generate_checkout_url
        url = generate_checkout_url(user_id, "standard")
        _reply(event.reply_token, PLAN_INFO.format(checkout_url=url))
        return

    _reply(event.reply_token, "写真を送ると無料でプロフィール診断します📸\nマッチングアプリで使っている写真を1枚送ってください。")


@line_handler.add(MessageEvent, message=ImageMessageContent)
def handle_image(event: MessageEvent) -> None:
    user_id = event.source.user_id
    message_id = event.message.id

    _reply(event.reply_token, "診断中です... 少々お待ちください📊")

    try:
        _run_async(_do_photo_diagnosis(user_id, message_id))
    except Exception as e:
        logger.error(f"写真診断エラー {user_id}: {e}")
        _push_message(user_id, "申し訳ありません、診断に失敗しました🙏\nもう一度送ってください。")


# ===================== 診断処理 =====================

async def _do_photo_diagnosis(user_id: str, message_id: str) -> None:
    from database.crud import AsyncSessionLocal, get_or_create_user, mark_free_diagnosis_used, increment_monthly_count, record_diagnosis
    from bots.profile_bot import diagnose_photo, format_diagnosis_result, check_usage_limit

    # LINE APIで画像取得
    with ApiClient(line_config) as api_client:
        blob_api = MessagingApiBlob(api_client)
        image_data: bytes = blob_api.get_message_content(message_id)

    async with AsyncSessionLocal() as session:
        user = await get_or_create_user(session, user_id)

        # 利用制限チェック
        if user.plan == "free" and user.free_diagnosis_used:
            limit_msg = check_usage_limit(user.plan, 0)
            _push_message(user_id, limit_msg)
            return

        monthly_count = user.monthly_profile_count
        limit_msg = check_usage_limit(user.plan, monthly_count)
        if limit_msg and user.plan != "free":
            _push_message(user_id, limit_msg)
            return

        # 診断実行（画像はここで使って破棄）
        score, points, potential_score = await diagnose_photo(image_data)
        del image_data  # 写真を即破棄

        is_free = user.plan == "free"

        # カウント更新
        if is_free:
            await mark_free_diagnosis_used(session, user_id)
        else:
            await increment_monthly_count(session, user_id, "profile")

        # スコアとテキストのみDB保存
        await record_diagnosis(
            session,
            line_user_id=user_id,
            bot_type="profile",
            score=score,
            feedback_summary="\n".join(points),
            is_free=is_free,
        )

    result_text = format_diagnosis_result(score, points, potential_score, is_free=is_free)
    _push_message(user_id, result_text)


# ===================== ヘルパー =====================

def _reply(reply_token: str, text: str) -> None:
    with ApiClient(line_config) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=text)])
        )


def _push_message(user_id: str, text: str) -> None:
    if len(text) > 4900:
        text = text[:4900] + "\n\n（文字数制限のため省略）"
    with ApiClient(line_config) as api_client:
        MessagingApi(api_client).push_message(
            PushMessageRequest(to=user_id, messages=[TextMessage(text=text)])
        )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "ZINQ Suite"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
