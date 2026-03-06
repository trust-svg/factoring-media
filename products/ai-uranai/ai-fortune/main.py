"""占いサロン Sion LINE Bot — メインエントリーポイント"""
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
    PushMessageRequest,
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

# メインイベントループへの参照（ワーカースレッドから非同期関数を呼ぶ用）
_main_loop: asyncio.AbstractEventLoop | None = None


def _run_async(coro):
    """ワーカースレッドから非同期関数を実行するヘルパー"""
    loop = _main_loop
    if loop is not None and loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=60)
    return asyncio.run(coro)


_scheduler = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    from database.crud import init_db
    from agents.scheduler import setup_scheduler

    await init_db()
    logger.info("データベース初期化完了")

    _scheduler = setup_scheduler()
    _scheduler.start()
    logger.info("スケジューラー起動完了")

    yield

    _scheduler.shutdown()
    logger.info("スケジューラー停止")


app = FastAPI(title="占いサロン Sion", lifespan=lifespan)

# STORES/管理エンドポイントを登録
from stores.webhook import router as stores_router  # noqa: E402
from admin.dashboard import router as admin_router  # noqa: E402
app.include_router(stores_router)
app.include_router(admin_router)


# ===================== プラン情報テキスト =====================

PLAN_INFO = (
    "🔮 占いサロン Sion — 鑑定メニュー\n\n"
    "【初回無料の簡易鑑定】\n"
    "・今のお悩みをメッセージで送るだけ\n"
    "・鑑定のエッセンスをお伝えします\n\n"
    "【本鑑定】¥4,980\n"
    "・恋愛・仕事・人生の転機を深く読み解きます\n"
    "・詳細レポートでお届け\n"
    "・STORES決済（あと払い・コンビニ払い・キャリア決済対応）\n\n"
    "▶ sion-salon.stores.jp\n\n"
    "まずは無料の簡易鑑定からお試しください✨"
)

ACCEPTED_MESSAGE = "鑑定を受け付けました。少々お待ちください✨"

HEARING_MESSAGE = (
    "🔮 簡易鑑定をご希望ですね✨\n\n"
    "今のお悩みや気になることを\n"
    "自由にメッセージで送ってください。\n\n"
    "例：\n"
    "・恋愛の行方が気になる\n"
    "・転職すべきか迷っている\n"
    "・人間関係に疲れている\n\n"
    "いただいた内容をもとに鑑定いたします🌙"
)


# ===================== Webhook エンドポイント =====================

@app.post("/webhook")
async def webhook(
    request: Request,
    x_line_signature: str = Header(alias="X-Line-Signature"),
) -> dict:
    global _main_loop
    _main_loop = asyncio.get_event_loop()

    body = await request.body()

    # 署名検証
    secret = os.environ["LINE_CHANNEL_SECRET"].encode("utf-8")
    sig = base64.b64encode(
        hmac.new(secret, body, hashlib.sha256).digest()
    ).decode()
    if not hmac.compare_digest(sig, x_line_signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    # ワーカースレッドで実行（イベントループをブロックしない）
    body_str = body.decode("utf-8")
    await asyncio.get_event_loop().run_in_executor(
        _executor, line_handler.handle, body_str, x_line_signature
    )
    return {"status": "ok"}


# ===================== LINE イベントハンドラ =====================

@line_handler.add(FollowEvent)
def handle_follow(event: FollowEvent) -> None:
    """友達追加時: ユーザー登録のみ（あいさつメッセージはLINE公式側で設定済み）"""
    user_id = event.source.user_id

    async def _register():
        from database.crud import AsyncSessionLocal, get_or_create_user
        async with AsyncSessionLocal() as session:
            await get_or_create_user(session, user_id)

    try:
        _run_async(_register())
    except Exception as e:
        logger.warning(f"ユーザー登録失敗 {user_id}: {e}")


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
        _reply(event.reply_token, reply)
        return

    # プラン確認
    if any(kw in user_message for kw in ("プラン", "料金", "値段", "課金")):
        _reply(event.reply_token, PLAN_INFO)
        return

    # 簡易鑑定リクエスト → 悩みを聞く（リッチメニューからの定型文対応）
    if any(kw in user_message for kw in ("簡易鑑定", "鑑定してほしい", "占ってほしい")):
        _reply(event.reply_token, HEARING_MESSAGE)
        return

    # 悩みのメッセージ → 受付メッセージを即返信 → バックグラウンドでAI生成
    _reply(event.reply_token, ACCEPTED_MESSAGE)

    try:
        _run_async(_generate_and_save(user_id, user_message))
    except Exception as e:
        logger.error(f"鑑定生成エラー {user_id}: {e}")
        _push_message(
            user_id,
            "申し訳ありません、鑑定の生成に問題が発生しました🙏\nもう一度お試しください。",
        )


async def _generate_and_save(user_id: str, user_message: str) -> None:
    """AI鑑定を生成してDBに保存する（バックグラウンド処理）"""
    from agents.fortune_agent import run_fortune_agent
    from database.crud import AsyncSessionLocal, record_reading

    result = await run_fortune_agent(user_id, user_message)

    # アップセルメッセージは監修不要 → 直接push送信
    if result.limit_reached:
        _push_message(user_id, result.draft_text)
        return

    # 下書きをDBに保存（status=pending → オーナーが監修）
    async with AsyncSessionLocal() as session:
        await record_reading(
            session,
            line_user_id=user_id,
            reading_type=result.reading_type,
            user_message=user_message,
            draft_text=result.draft_text,
            status="pending",
        )

    logger.info(f"鑑定保留: {user_id} ({result.reading_type})")


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


def _push_message(user_id: str, text: str) -> None:
    """ユーザーにプッシュメッセージを送信する"""
    with ApiClient(line_config) as api_client:
        line_api = MessagingApi(api_client)
        line_api.push_message(
            PushMessageRequest(
                to=user_id,
                messages=[TextMessage(text=text)],
            )
        )


# ===================== 手動トリガー =====================

@app.post("/admin/trigger-threads")
async def trigger_threads(request: Request, key: str = "") -> dict:
    """Threads投稿を手動トリガー（管理者用）"""
    if key != os.environ.get("ADMIN_SECRET_KEY", ""):
        raise HTTPException(status_code=403, detail="Forbidden")
    data = await request.json()
    slot = data.get("slot", "morning")
    if slot not in ("morning", "afternoon", "evening"):
        raise HTTPException(status_code=400, detail="Invalid slot")

    # 診断情報
    has_token = bool(os.environ.get("THREADS_ACCESS_TOKEN"))
    has_user_id = bool(os.environ.get("THREADS_USER_ID"))
    if not has_token or not has_user_id:
        return {"status": "error", "reason": "env_missing",
                "THREADS_ACCESS_TOKEN": has_token, "THREADS_USER_ID": has_user_id}

    from agents.content_agent import run_content_agent
    try:
        result = await run_content_agent(slot)
        return {"status": "ok", "slot": slot, "result": result[:200]}
    except Exception as e:
        return {"status": "error", "slot": slot, "error": str(e)}


# ===================== ヘルスチェック =====================

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "占いサロン Sion"}


@app.get("/admin/scheduler-status")
async def scheduler_status(key: str = "") -> dict:
    """スケジューラーの状態を確認（管理者用）"""
    if key != os.environ.get("ADMIN_SECRET_KEY", ""):
        raise HTTPException(status_code=403, detail="Forbidden")
    if _scheduler is None:
        return {"status": "not_initialized"}
    jobs = []
    for job in _scheduler.get_jobs():
        next_run = job.next_run_time
        if next_run:
            from zoneinfo import ZoneInfo
            next_run = next_run.astimezone(ZoneInfo("Asia/Tokyo"))
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": str(next_run) if next_run else None,
        })
    return {
        "status": "running" if _scheduler.running else "stopped",
        "jobs": jobs,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
