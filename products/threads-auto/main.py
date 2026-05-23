"""Threads完全自動運用システム — メインエントリ

FastAPI + APScheduler で6エージェントを統合管理
"""

import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from agents import researcher, analyst, writer, poster, fetcher, supervisor
from config import HOST, PORT, POST_TIMESLOTS, STATE_DIR
from state_manager import (
    activate_kill_switch,
    deactivate_kill_switch,
    get_post_history,
    get_queue,
    is_kill_switch_active,
    get_analyst_feedback,
)
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(STATE_DIR / "system.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="Asia/Tokyo")
templates = Jinja2Templates(directory="templates")


# ------------------------------------------------------------------
# Pydantic スキーマ
# ------------------------------------------------------------------


class ContactForm(BaseModel):
    name: str
    company: str
    email: str
    message: str


# ------------------------------------------------------------------
# スケジュール登録
# ------------------------------------------------------------------


def setup_scheduler() -> None:
    """APSchedulerにジョブを登録"""

    # ① リサーチャー: 毎日7:00
    scheduler.add_job(
        researcher.run,
        CronTrigger(hour=7, minute=0),
        id="researcher",
        name="リサーチャー",
        replace_existing=True,
    )

    # ② アナリスト: 毎日7:30
    scheduler.add_job(
        analyst.run,
        CronTrigger(hour=7, minute=30),
        id="analyst",
        name="アナリスト",
        replace_existing=True,
    )

    # ③ ライター: 毎日8:00
    scheduler.add_job(
        writer.run,
        CronTrigger(hour=8, minute=0),
        id="writer",
        name="ライター",
        replace_existing=True,
    )

    # ④ ポスター: タイムスロットごとに実行
    for i, slot in enumerate(POST_TIMESLOTS):
        hour, minute = slot.split(":")
        h = int(hour)
        m = int(minute)
        # 24:00 → 翌0:00として処理
        if h >= 24:
            h = h - 24
        scheduler.add_job(
            poster.run,
            CronTrigger(hour=h, minute=m),
            id=f"poster_{i}",
            name=f"ポスター({slot})",
            replace_existing=True,
        )

    # ⑤ フェッチャー: 毎日6:00（前日分のメトリクスを取得）
    scheduler.add_job(
        fetcher.run,
        CronTrigger(hour=6, minute=0),
        id="fetcher",
        name="フェッチャー",
        replace_existing=True,
    )

    # ⑥ スーパーバイザー: 5分ごとヘルスチェック
    scheduler.add_job(
        supervisor.run,
        IntervalTrigger(minutes=5),
        id="supervisor_health",
        name="スーパーバイザー(ヘルスチェック)",
        replace_existing=True,
    )

    # ⑥ スーパーバイザー: 毎日23:00に日次サマリー
    scheduler.add_job(
        supervisor.daily_summary,
        CronTrigger(hour=23, minute=0),
        id="supervisor_daily",
        name="スーパーバイザー(日次サマリー)",
        replace_existing=True,
    )

    logger.info("スケジューラー設定完了: %d ジョブ登録", len(scheduler.get_jobs()))


# ------------------------------------------------------------------
# FastAPI
# ------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_scheduler()
    scheduler.start()
    logger.info("=== Threads自動運用システム起動 ===")
    yield
    scheduler.shutdown()
    logger.info("=== システム停止 ===")


app = FastAPI(title="Threads Auto", lifespan=lifespan)


@app.post("/contact")
async def contact(form: ContactForm):
    """ASPお問い合わせフォーム → Telegram通知"""
    from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

    text = (
        f"📬 ASPお問い合わせ\n\n"
        f"名前: {form.name}\n"
        f"会社: {form.company}\n"
        f"メール: {form.email}\n\n"
        f"内容:\n{form.message}"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
        )
    return {"status": "ok"}


@app.get("/go")
async def affiliate_redirect():
    """転職AGENT Navi アフィリエイトリダイレクト"""
    from fastapi.responses import RedirectResponse

    return RedirectResponse("https://px.a8.net/svt/ejp?a8mat=4AZLSE+3WIBJM+5BJK+5Z6WY")


@app.get("/", response_class=HTMLResponse)
async def landing():
    from pathlib import Path

    return HTMLResponse(
        content=Path("templates/landing.html").read_text(encoding="utf-8")
    )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    history = get_post_history(limit=50)
    queue = get_queue()
    feedback = get_analyst_feedback()
    jobs = [
        {"id": j.id, "name": j.name, "next_run": str(j.next_run_time)}
        for j in scheduler.get_jobs()
    ]
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "history": list(reversed(history)),
            "queue": queue,
            "feedback": feedback,
            "jobs": jobs,
            "kill_switch": is_kill_switch_active(),
            "stats": {
                "total_posts": len(get_post_history()),
                "queue_size": len(queue),
            },
        },
    )


@app.get("/api/status")
async def api_status():
    return JSONResponse(
        {
            "kill_switch": is_kill_switch_active(),
            "queue_size": len(get_queue()),
            "total_posts": len(get_post_history()),
            "jobs": [
                {"id": j.id, "name": j.name, "next_run": str(j.next_run_time)}
                for j in scheduler.get_jobs()
            ],
        }
    )


@app.post("/api/kill-switch/{action}")
async def toggle_kill_switch(action: str):
    if action == "on":
        activate_kill_switch("手動で有効化")
        return {"status": "KILL SWITCH ON"}
    elif action == "off":
        deactivate_kill_switch()
        return {"status": "KILL SWITCH OFF"}
    return {"error": "action must be 'on' or 'off'"}


@app.post("/api/trigger/{agent}")
async def trigger_agent(agent: str):
    """手動でエージェントを実行"""
    agents_map = {
        "researcher": researcher.run,
        "analyst": analyst.run,
        "writer": writer.run,
        "poster": poster.run,
        "fetcher": fetcher.run,
        "supervisor": supervisor.run,
    }
    fn = agents_map.get(agent)
    if not fn:
        return JSONResponse({"error": f"Unknown agent: {agent}"}, status_code=400)

    asyncio.create_task(fn())
    return {"status": f"{agent} triggered"}


# ------------------------------------------------------------------
# OAuth認証フロー（長期トークン取得用）
# ------------------------------------------------------------------


@app.get("/auth/threads")
async def auth_threads():
    """Step 1: Threads認証ページにリダイレクト"""
    from config import THREADS_APP_ID
    from config import PUBLIC_URL

    base = PUBLIC_URL or f"http://{HOST}:{PORT}"
    redirect_uri = f"{base}/auth/threads/callback"
    scope = "threads_basic,threads_content_publish,threads_manage_insights,threads_manage_replies"
    auth_url = (
        f"https://threads.net/oauth/authorize"
        f"?client_id={THREADS_APP_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&scope={scope}"
        f"&response_type=code"
    )
    return RedirectResponse(auth_url)


@app.get("/auth/threads/callback")
async def auth_threads_callback(code: str = ""):
    """Step 2: 認証コードを受け取り、短期→長期トークンに変換"""
    from config import THREADS_APP_ID, THREADS_APP_SECRET

    if not code:
        return JSONResponse({"error": "No code received"}, status_code=400)

    from config import PUBLIC_URL

    base = PUBLIC_URL or f"http://{HOST}:{PORT}"
    redirect_uri = f"{base}/auth/threads/callback"

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 2a: 認証コード → 短期トークン
        resp = await client.post(
            "https://graph.threads.net/oauth/access_token",
            data={
                "client_id": THREADS_APP_ID,
                "client_secret": THREADS_APP_SECRET,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )
        if resp.status_code != 200:
            return JSONResponse(
                {"error": "Token exchange failed", "detail": resp.text}, status_code=400
            )

        short_token_data = resp.json()
        short_token = short_token_data.get("access_token", "")
        user_id = short_token_data.get("user_id", "")

        # Step 2b: 短期トークン → 長期トークン
        resp2 = await client.get(
            "https://graph.threads.net/access_token",
            params={
                "grant_type": "th_exchange_token",
                "client_secret": THREADS_APP_SECRET,
                "access_token": short_token,
            },
        )
        if resp2.status_code != 200:
            return JSONResponse(
                {
                    "error": "Long-lived token exchange failed",
                    "short_token": short_token,
                    "user_id": user_id,
                    "detail": resp2.text,
                },
                status_code=400,
            )

        long_token_data = resp2.json()
        long_token = long_token_data.get("access_token", "")
        expires_in = long_token_data.get("expires_in", 0)

    logger.info(
        "長期トークン取得成功！ user_id=%s, expires_in=%d秒", user_id, expires_in
    )

    return JSONResponse(
        {
            "status": "success",
            "user_id": user_id,
            "access_token": long_token,
            "expires_in_days": expires_in // 86400,
            "message": "このaccess_tokenを.envのTHREADS_ACCESS_TOKENに設定してください",
        }
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
