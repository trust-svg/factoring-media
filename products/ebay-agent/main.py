"""eBay Agent Hub — FastAPI メインサーバー

統合ダッシュボード + REST API + AIエージェントエンドポイント
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))

import uvicorn
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import (
    APP_HOST,
    APP_PORT,
    DEAL_WATCHER_DB,
    EBAY_FEE_RATE,
    PAYONEER_FEE_RATE,
    PRICE_CHECK_INTERVAL_HOURS,
    SHOPIFY_WEBHOOK_SECRET,
    STATIC_DIR,
    TEMPLATES_DIR,
    MONTHLY_REVENUE_TARGET_JPY,
    MONTHLY_MARGIN_TARGET_PCT,
    MONTHLY_PROFIT_TARGET_JPY,
)
from database.models import get_db, init_db, Listing, Procurement
from database import crud
from agents.orchestrator import run_agent
from tools.handlers import handle_tool_call

# ── ログ設定 ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("ebay-agent")


# ── アプリ初期化 ──────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("eBay Agent Hub 起動中...")
    init_db()
    logger.info("データベース初期化完了")

    # スケジューラー起動
    scheduler = _start_scheduler()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)
    logger.info("eBay Agent Hub シャットダウン")


def _start_scheduler():
    """APScheduler で定期タスクを設定"""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
        from pricing.monitor import run_price_monitor
        from comms.scheduled_jobs import (
            send_morning_digest,
            send_weekly_report,
            auto_sync_sales,
            auto_sync_and_close_shopify,
        )
        from comms.report_generator import run_weekly_report, run_monthly_report

        scheduler = BackgroundScheduler()

        # 競合価格モニター（6時間間隔）
        scheduler.add_job(
            run_price_monitor,
            "interval",
            hours=PRICE_CHECK_INTERVAL_HOURS,
            kwargs={"limit": 30},
            id="price_monitor",
            name="競合価格モニター",
        )

        # 朝のダイジェスト（毎日9:00 JST）
        scheduler.add_job(
            send_morning_digest,
            CronTrigger(hour=9, minute=0, timezone="Asia/Tokyo"),
            id="morning_digest",
            name="朝のダイジェスト",
        )

        # 週間レポート（毎週月曜10:00 JST）
        scheduler.add_job(
            send_weekly_report,
            CronTrigger(day_of_week="mon", hour=10, minute=0, timezone="Asia/Tokyo"),
            id="weekly_report",
            name="週間レポート",
        )

        # 週次分析レポート（毎週月曜10:30 JST — 週間レポート通知の後に生成）
        scheduler.add_job(
            run_weekly_report,
            CronTrigger(day_of_week="mon", hour=10, minute=30, timezone="Asia/Tokyo"),
            id="weekly_analytics_report",
            name="週次分析レポート",
        )

        # 月次分析レポート（毎月1日 10:00 JST）
        scheduler.add_job(
            run_monthly_report,
            CronTrigger(day=1, hour=10, minute=0, timezone="Asia/Tokyo"),
            id="monthly_analytics_report",
            name="月次分析レポート",
        )

        # 売上自動同期（3時間ごと）
        scheduler.add_job(
            auto_sync_sales,
            IntervalTrigger(hours=3),
            id="auto_sync_sales",
            name="売上自動同期",
        )

        # eBay在庫同期（6時間ごと）— listings.fetched_at を更新し死に筒判定の鮮度を保つ。
        # これが無いと quantity=1 が古いスナップショットで固定され、死に筒Refresh が
        # 既に終了済みSKUばかり選んで sku_missing 連発になる（2026-03〜05 の事故）。
        def _run_inventory_sync():
            import asyncio

            enabled = os.getenv("INVENTORY_SYNC_ENABLED", "true").lower() == "true"
            if not enabled:
                return
            try:
                from tools.handlers import handle_tool_call

                loop = asyncio.new_event_loop()
                result_json = loop.run_until_complete(
                    handle_tool_call("check_inventory", {"out_of_stock_only": False})
                )
                import json as _json

                result = _json.loads(result_json)
                if "error" in result:
                    logger.warning(f"eBay在庫同期エラー: {result['error']}")
                else:
                    logger.info(
                        f"eBay在庫同期: total={result.get('total', 0)}件 / "
                        f"在庫切れ={result.get('out_of_stock', 0)}件"
                    )
            except Exception as e:
                logger.exception(f"eBay在庫同期失敗: {e}")

        scheduler.add_job(
            _run_inventory_sync,
            IntervalTrigger(hours=6),
            id="ebay_inventory_sync",
            name="eBay在庫同期",
            next_run_time=datetime.utcnow() + timedelta(seconds=30),
        )

        # Instagram コンテンツ自動生成（毎日10:00 JST）
        from instagram.scheduler import (
            auto_generate_instagram_content,
            sync_instagram_analytics,
        )

        scheduler.add_job(
            auto_generate_instagram_content,
            CronTrigger(hour=10, minute=0, timezone="Asia/Tokyo"),
            id="instagram_content",
            name="Instagram自動生成",
        )

        # Instagram 分析同期（毎日23:00 JST）
        scheduler.add_job(
            sync_instagram_analytics,
            CronTrigger(hour=23, minute=0, timezone="Asia/Tokyo"),
            id="instagram_analytics",
            name="Instagram分析同期",
        )

        # カテゴリ自動拡張（毎週水曜 11:00 JST）
        def _run_category_expansion():
            import asyncio
            from research.category_expansion import run_category_expansion_pipeline

            try:
                loop = asyncio.new_event_loop()
                result = loop.run_until_complete(
                    run_category_expansion_pipeline(
                        notify=True, auto_source=True, top_n=3
                    )
                )
                logger.info(
                    f"カテゴリ拡張完了: {result.get('categories_evaluated', 0)}カテゴリ分析"
                )
            except Exception as e:
                logger.exception(f"カテゴリ拡張失敗: {e}")

        scheduler.add_job(
            _run_category_expansion,
            CronTrigger(day_of_week="wed", hour=11, minute=0, timezone="Asia/Tokyo"),
            id="category_expansion",
            name="カテゴリ自動拡張",
        )

        # バイヤーメッセージ自動同期（5分間隔）
        def _sync_buyer_messages():
            import asyncio
            from chat.service import sync_messages
            from database.models import get_db as _get_db

            try:
                db = _get_db()
                loop = asyncio.new_event_loop()
                result = loop.run_until_complete(sync_messages(db, days=3))
                logger.info(f"メッセージ同期: 新規{result.get('new', 0)}件")
                db.close()
            except Exception as e:
                logger.warning(f"メッセージ同期失敗: {e}")

        scheduler.add_job(
            _sync_buyer_messages,
            IntervalTrigger(minutes=5),
            id="buyer_message_sync",
            name="バイヤーメッセージ同期",
        )

        # Shopify同期（30分間隔）: 未同期出品のpush + 売れた商品のclose
        scheduler.add_job(
            auto_sync_and_close_shopify,
            "interval",
            minutes=30,
            id="shopify_sync",
            name="Shopify在庫同期",
        )

        # 未返信タイムアウト自動返信チェック（5分間隔）
        def _check_no_reply_timeout():
            from chat.auto_message import check_no_reply_timeout
            from database.models import get_db as _get_db

            try:
                db = _get_db()
                results = check_no_reply_timeout(db)
                if results:
                    sent = sum(1 for r in results if r.get("sent"))
                    logger.info(f"未返信自動返信: {sent}/{len(results)}件送信")
                db.close()
            except Exception as e:
                logger.warning(f"未返信自動返信チェック失敗: {e}")

        scheduler.add_job(
            _check_no_reply_timeout,
            IntervalTrigger(minutes=5),
            id="no_reply_timeout",
            name="未返信タイムアウト自動返信",
        )

        # 死に筒Refresh（06:00-23:00 JST、20分ごとに1-2件＋ジッター／内部でWindow/dailyCap制御）
        def _run_refresh_slot():
            import asyncio
            from listing.refresh import run_refresh_slot

            # 環境変数でON/OFF（初期はOFF、ドライラン完了後にONへ切替）
            enabled = os.getenv("LISTING_REFRESH_ENABLED", "false").lower() == "true"
            if not enabled:
                return
            try:
                loop = asyncio.new_event_loop()
                result = loop.run_until_complete(run_refresh_slot(dry_run=False))
                if not result.get("skipped"):
                    logger.info(
                        f"死に筒Refresh: {result.get('processed')}件処理 日次累計{result.get('daily_applied')}"
                    )
            except Exception as e:
                logger.warning(f"死に筒Refresh失敗: {e}")

        scheduler.add_job(
            _run_refresh_slot,
            IntervalTrigger(minutes=20, jitter=600),  # 20分±10分のジッター
            id="listing_refresh_slot",
            name="死に筒Refresh",
        )

        # 無在庫出品パイプライン（毎日 09:00 JST）
        # eBay高額売れ筋スキャン → 国内逆検索 → Telegram候補通知
        def _run_dropship_pipeline():
            import asyncio

            enabled = os.getenv("DROPSHIP_PIPELINE_ENABLED", "false").lower() == "true"
            if not enabled:
                return
            try:
                from research.hot_expensive import scan_top_categories
                from sourcing.reverse_match import find_jp_candidates
                from comms.dropship_notify import send_dropship_digest
                from database.models import get_db as _get_db

                db = _get_db()
                try:
                    hot = scan_top_categories(db)
                    logger.info(f"無在庫Pipeline: hot_expensive {len(hot)}件")

                    loop = asyncio.new_event_loop()
                    cands = loop.run_until_complete(find_jp_candidates(db))
                    logger.info(f"無在庫Pipeline: dropship_candidates {len(cands)}件")

                    loop.run_until_complete(send_dropship_digest(db))
                finally:
                    db.close()
            except Exception as e:
                logger.exception(f"無在庫Pipeline失敗: {e}")

        scheduler.add_job(
            _run_dropship_pipeline,
            CronTrigger(hour=9, minute=0, timezone="Asia/Tokyo"),
            id="dropship_pipeline",
            name="無在庫出品パイプライン",
        )

        # ── リピート購入エンジン Phase 1 ───────────────────
        # REPEAT_ENGINE_ENABLED=false の間はジョブは登録するが内部で early-return する
        # （関数側でフラグ参照）。これにより環境変数の切替だけで有効化できる。
        from chat.repeat_engine import (
            draft_pending_post_feedback,
            refresh_eligibility,
            rebuild_buyer_segments,
        )

        scheduler.add_job(
            refresh_eligibility,
            CronTrigger(hour=2, minute=0, timezone="Asia/Tokyo"),
            id="repeat_refresh_eligibility",
            name="リピート: eligibility再計算",
        )
        scheduler.add_job(
            rebuild_buyer_segments,
            CronTrigger(hour=2, minute=30, timezone="Asia/Tokyo"),
            id="repeat_rebuild_segments",
            name="リピート: buyer_segments再構築",
        )
        scheduler.add_job(
            draft_pending_post_feedback,
            IntervalTrigger(minutes=15),
            id="repeat_post_feedback_drafter",
            name="リピート: D7下書き生成",
        )

        scheduler.start()
        logger.info(
            f"スケジューラー起動: 価格モニター {PRICE_CHECK_INTERVAL_HOURS}h間隔 + "
            f"朝ダイジェスト 9:00 + 週間レポート Mon 10:00 + 週次分析 Mon 10:30 + "
            f"月次分析 1日 10:00 + 売上同期 3h間隔 + "
            f"eBay在庫同期 6h間隔（ENV:INVENTORY_SYNC_ENABLED制御） + "
            f"Instagram生成 10:00 + Instagram分析 23:00 + カテゴリ拡張 Wed 11:00 + "
            f"メッセージ同期 5min間隔 + 未返信自動返信 5min間隔 + "
            f"死に筒Refresh 20min間隔（ENV:LISTING_REFRESH_ENABLED制御） + "
            f"無在庫Pipeline 9:00 JST（ENV:DROPSHIP_PIPELINE_ENABLED制御） + "
            f"リピートEngine eligibility 02:00 + segments 02:30 + drafter 15min間隔"
            f"（ENV:REPEAT_ENGINE_ENABLED制御）"
        )
        return scheduler
    except ImportError:
        logger.warning(
            "APScheduler 未インストール — スケジューラー無効。pip install apscheduler で有効化できます。"
        )
        return None


app = FastAPI(
    title="eBay Agent Hub",
    description="eBay輸出ビジネス統合AIエージェント",
    version="1.0.0",
    lifespan=lifespan,
)

# グローバル例外ハンドラー（デバッグ用）
import traceback as _tb


@app.exception_handler(Exception)
async def _global_exc_handler(request: Request, exc: Exception):
    logger.error(
        f"★ UNHANDLED {request.method} {request.url.path}: {exc}\n{''.join(_tb.format_exception(type(exc), exc, exc.__traceback__))}"
    )
    return JSONResponse(status_code=500, content={"detail": str(exc)})


# 静的ファイル + テンプレート
STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 静的ファイルのキャッシュ無効化（開発用） — raw ASGI middleware（BaseHTTPMiddleware不使用）
from starlette.types import ASGIApp, Receive, Scope, Send


class CacheStaticMiddleware:
    """静的ファイルにブラウザキャッシュヘッダーを設定する。

    JS/CSS: 1時間キャッシュ（開発中は短め、本番では延長可）
    画像: 7日間キャッシュ（ebayimg.comはプロキシしないので対象外）
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http" and scope["path"].startswith("/static/"):
            path = scope["path"].lower()
            if any(
                path.endswith(ext)
                for ext in (".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico", ".gif")
            ):
                max_age = 604800  # 7日
            elif any(path.endswith(ext) for ext in (".js", ".css")):
                max_age = 3600  # 1時間
            else:
                max_age = 3600

            async def send_with_cache(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append(
                        (b"cache-control", f"public, max-age={max_age}".encode())
                    )
                    message["headers"] = headers
                await send(message)

            await self.app(scope, receive, send_with_cache)
        else:
            await self.app(scope, receive, send)


app.add_middleware(CacheStaticMiddleware)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.auto_reload = True


def render(request: Request, template: str, context: dict = None):
    """Starlette 1.0互換テンプレートレンダー"""
    ctx = context or {}
    return templates.TemplateResponse(request=request, name=template, context=ctx)


# Chat API Router
from chat.router import router as chat_router

app.include_router(chat_router)


# ── ページルート ──────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def overview_page(request: Request):
    db = get_db()
    try:
        stats = crud.get_dashboard_stats(db)
        return render(request, "pages/overview.html", {"stats": stats})
    finally:
        db.close()


# ── 統合ページ (v2 メニュー構成) ──────────────────────────


@app.get("/listings", response_class=HTMLResponse)
async def listings_page(request: Request):
    """在庫・価格（Inventory + Pricing 統合）"""
    db = get_db()
    try:
        listings = crud.get_all_listings(db)
        return render(request, "pages/listings.html", {"listings": listings})
    finally:
        db.close()


@app.get("/procurement", response_class=HTMLResponse)
async def procurement_page(request: Request):
    """/procurement → /sourcing リダイレクト（統合済み）"""
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/sourcing", status_code=301)


@app.get("/research", response_class=HTMLResponse)
async def research_page(request: Request):
    """リサーチ（Discovery + Deal Watcher 統合）"""
    import httpx

    data = _get_deal_watcher_data()
    scan_status = {"last_run": None, "running": False}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://127.0.0.1:8001/api/status", timeout=3)
            scan_status = resp.json()
    except Exception:
        pass
    return render(
        request,
        "pages/research.html",
        {**data, "scan_status": scan_status, "interval": 3},
    )


@app.get("/sales", response_class=HTMLResponse)
async def sales_page(request: Request):
    """売上・利益（Profit + Analytics 統合）"""
    return render(request, "pages/sales.html")


# ── 旧URL → 新URLリダイレクト ──────────────────────────


@app.get("/inventory", response_class=HTMLResponse)
async def inventory_redirect():
    return RedirectResponse(url="/listings", status_code=301)


@app.get("/pricing", response_class=HTMLResponse)
async def pricing_redirect():
    return RedirectResponse(url="/listings?tab=pricing", status_code=301)


@app.get("/sourcing", response_class=HTMLResponse)
async def sourcing_page(request: Request):
    """仕入れ管理（仕入れ記録 + 在庫台帳 統合ページ）"""
    return render(request, "pages/sourcing.html")


@app.get("/analytics")
async def analytics_redirect():
    """売上分析は売上・利益に統合 — リダイレクト"""
    return RedirectResponse(url="/sales?tab=analytics", status_code=301)


@app.get("/messages")
async def messages_redirect():
    """旧メッセージURL → /chat にリダイレクト"""
    return RedirectResponse(url="/chat", status_code=302)


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    """バイヤーメッセージ（チャットUI）"""
    return render(request, "pages/chat.html")


@app.get("/chat/settings", response_class=HTMLResponse)
async def chat_settings_page(request: Request):
    """自動メッセージ設定"""
    return render(request, "pages/chat_settings.html")


# ── 無在庫候補 出品（eBay+eShip 同時） ────────────────────


@app.get("/dropship/candidates", response_class=HTMLResponse)
async def dropship_candidates_page(request: Request):
    """無在庫候補一覧（eBay+eShip 同時出品ボタン付き）"""
    from sqlalchemy import desc
    from database.models import DropshipCandidate, get_db as _get_db

    db = _get_db()
    try:
        rows = (
            db.query(DropshipCandidate)
            .filter(DropshipCandidate.status.in_(["pending", "approved"]))
            .order_by(desc(DropshipCandidate.projected_profit_usd))
            .limit(50)
            .all()
        )
        return render(request, "pages/dropship_candidates.html", {"candidates": rows})
    finally:
        db.close()


@app.post("/api/dropship/publish/{candidate_id}")
async def api_dropship_publish(candidate_id: int, request: Request):
    """候補1件を eBay ドラフト + eShip 在庫に同時登録する。

    ?publish=1 を付けると eBay も即公開（デフォルトはドラフトのみ）。
    """
    from services.dropship_publish import publish_dropship_candidate
    from database.models import get_db as _get_db

    publish_immediately = request.query_params.get("publish") == "1"
    db = _get_db()
    try:
        result = await publish_dropship_candidate(
            db, candidate_id, publish_immediately=publish_immediately
        )
    finally:
        db.close()
    return JSONResponse(result)


@app.post("/api/dropship/reject/{candidate_id}")
async def api_dropship_reject(candidate_id: int):
    """候補を却下（status=rejected）する。"""
    from database.models import DropshipCandidate, get_db as _get_db

    db = _get_db()
    try:
        cand = db.get(DropshipCandidate, candidate_id)
        if not cand:
            return JSONResponse(
                {"status": "error", "message": "not found"}, status_code=404
            )
        cand.status = "rejected"
        db.commit()
        return {"status": "ok", "candidate_id": candidate_id}
    finally:
        db.close()


# ── eBay Platform Notifications Webhook ──────────────────


@app.get("/webhook/ebay")
async def ebay_webhook_verify(challenge_code: str = ""):
    """eBay Webhook検証チャレンジに応答する。"""
    import os
    from chat.webhook import verify_challenge

    verification_token = os.getenv("EBAY_VERIFICATION_TOKEN", "")
    endpoint_url = os.getenv("EBAY_WEBHOOK_URL", "")
    if not challenge_code:
        return {"status": "ready"}
    response_hash = verify_challenge(challenge_code, verification_token, endpoint_url)
    return {"challengeResponse": response_hash}


@app.post("/webhook/ebay")
async def ebay_webhook_receive(request: Request):
    """eBay Platform Notificationsを受信して処理する。"""
    from chat.webhook import handle_notification

    body = await request.body()
    body_str = body.decode("utf-8")
    logger.info(f"eBay Webhook受信: {len(body_str)} bytes")
    result = await handle_notification(body_str)
    return result


# ── Telegram Webhook（リピート購入エンジン承認） ─────────


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """Telegram setWebhook の受信エンドポイント。

    承認カードの inline_keyboard コールバック (`ro:approve:<id>` 等) のみ処理する。
    通常のメッセージは現状無視（必要なら edit_pending 待ち実装で拾う）。
    """
    from config import TELEGRAM_WEBHOOK_SECRET
    from comms.telegram_approval import (
        answer_callback_query,
        edit_card_status,
        parse_callback_query,
    )
    from chat.repeat_engine import handle_telegram_action

    if TELEGRAM_WEBHOOK_SECRET:
        provided = request.headers.get("x-telegram-bot-api-secret-token", "")
        if provided != TELEGRAM_WEBHOOK_SECRET:
            logger.warning("Telegram webhook: secret token mismatch")
            raise HTTPException(status_code=403, detail="forbidden")

    try:
        update = await request.json()
    except Exception:
        logger.warning("Telegram webhook: invalid JSON body")
        return JSONResponse({"ok": True})

    parsed = parse_callback_query(update)
    if not parsed:
        return JSONResponse({"ok": True})

    action = parsed["action"]
    offer_id = parsed["offer_id"]
    cb = {"from": parsed["from"], "message": parsed["message"]}

    try:
        result = handle_telegram_action(action, offer_id, cb)
    except Exception:
        logger.exception(
            f"telegram_webhook handler crashed action={action} offer={offer_id}"
        )
        result = {"error": "handler_crashed"}

    # UI フィードバック（ベストエフォート）
    try:
        await answer_callback_query(
            parsed["callback_query_id"],
            text=_describe_action_result(action, result),
        )
        msg = parsed.get("message") or {}
        chat_id = (msg.get("chat") or {}).get("id")
        message_id = msg.get("message_id")
        if chat_id and message_id:
            await edit_card_status(
                chat_id, message_id, _format_status_line(action, result)
            )
    except Exception:
        logger.exception("telegram UI feedback failed")

    return JSONResponse({"ok": True, "action": action, "result": result})


def _describe_action_result(action: str, result: dict) -> str:
    if result.get("error"):
        return f"⚠️ {result['error']}"
    if action == "approve":
        if result.get("dry_run"):
            return "✅ Sent (DRY-RUN)"
        if result.get("sent"):
            return "✅ Sent"
        return "⚠️ failed"
    if action == "reject":
        return "❌ Rejected"
    if action == "edit":
        return "✏️ Edit pending"
    return "ok"


def _format_status_line(action: str, result: dict) -> str:
    base = _describe_action_result(action, result)
    if result.get("error"):
        return f"<b>{base}</b>"
    if action == "approve" and result.get("dry_run"):
        return f"<b>{base}</b> — DB のみ更新（eBay 未送信）"
    return f"<b>{base}</b>"


# ── リピート購入エンジン管理 API ─────────────────────


@app.get("/api/repeat/outbound-queue")
async def repeat_outbound_queue(status: str = "", limit: int = 50):
    """承認待ち/送信済みなどステータス別に outbound_offers を取得する。"""
    from database.models import OutboundOffer

    db = get_db()
    try:
        q = db.query(OutboundOffer).order_by(OutboundOffer.created_at.desc())
        if status:
            q = q.filter(OutboundOffer.status == status)
        rows = q.limit(min(max(limit, 1), 500)).all()
        return {
            "items": [
                {
                    "id": r.id,
                    "buyer_username": r.buyer_username,
                    "trigger": r.trigger,
                    "status": r.status,
                    "past_order_item_id": r.past_order_item_id,
                    "draft_subject": r.draft_subject,
                    "draft_body": r.draft_body,
                    "compliance_flags": r.compliance_flags_json,
                    "due_at": r.due_at.isoformat() if r.due_at else None,
                    "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "error_message": r.error_message,
                }
                for r in rows
            ]
        }
    finally:
        db.close()


@app.post("/api/repeat/opt-out/{buyer}")
async def repeat_opt_out(buyer: str, reason: str = "manual"):
    """指定バイヤーを opt-out（BuyerExclude + 全 BuyerSegment に伝播）。"""
    from chat.repeat_engine import opt_out_buyer

    return opt_out_buyer(buyer, reason=reason)


@app.get("/api/repeat/kpi")
async def repeat_kpi():
    """Phase 1 最小 KPI: ステータス別件数 + 7日後購入率の雛形。"""
    from database.models import OutboundOffer
    from sqlalchemy import func as _func

    db = get_db()
    try:
        rows = (
            db.query(OutboundOffer.status, _func.count(OutboundOffer.id))
            .group_by(OutboundOffer.status)
            .all()
        )
        counts = {s: c for s, c in rows}
        sent = counts.get("sent", 0)
        converted = (
            db.query(OutboundOffer)
            .filter(
                OutboundOffer.status == "sent",
                OutboundOffer.resulted_in_purchase_order_id != "",
            )
            .count()
        )
        return {
            "counts_by_status": counts,
            "sent": sent,
            "converted": converted,
            "conversion_rate": (converted / sent) if sent else 0.0,
        }
    finally:
        db.close()


@app.get("/agent", response_class=HTMLResponse)
async def agent_page(request: Request):
    return render(request, "pages/agent.html")


@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    """分析レポート"""
    return render(request, "pages/reports.html")


@app.get("/api/reports")
async def api_report_list(type: str = ""):
    """レポート一覧API"""
    from comms.report_generator import get_report_list

    reports = get_report_list(report_type=type)
    return {"reports": reports}


@app.get("/api/reports/{report_id}")
async def api_report_detail(report_id: int):
    """レポート詳細API"""
    from comms.report_generator import get_report_by_id

    report = get_report_by_id(report_id)
    if not report:
        return JSONResponse(status_code=404, content={"error": "Report not found"})
    return report


@app.post("/api/reports/generate")
async def api_generate_report(request: Request):
    """レポート手動生成API"""
    body = await request.json()
    report_type = body.get("type", "weekly")
    if report_type not in ("weekly", "monthly"):
        return JSONResponse(
            status_code=400, content={"error": "type must be 'weekly' or 'monthly'"}
        )
    from comms.report_generator import generate_report

    data = generate_report(report_type)
    return data


@app.get("/instagram", response_class=HTMLResponse)
async def instagram_page(request: Request):
    return render(request, "pages/instagram.html")


# ── Deal Watcher ──────────────────────────────────────────


def _get_deal_watcher_data():
    """Read deal-watcher DB and return grouped listings with eBay enrichment."""
    import os
    import sqlite3

    dw_db = DEAL_WATCHER_DB
    if not os.path.exists(dw_db):
        return {
            "groups": [],
            "keywords": [],
            "kw_count": 0,
            "listing_count": 0,
            "hidden_count": 0,
        }

    conn = sqlite3.connect(dw_db)
    conn.row_factory = sqlite3.Row

    keywords = [
        dict(r) for r in conn.execute("SELECT * FROM keywords ORDER BY name").fetchall()
    ]
    kw_count = sum(1 for k in keywords if k["active"])
    listing_count = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    hidden_count = conn.execute(
        "SELECT COUNT(*) FROM listings WHERE COALESCE(hidden,0)=1"
    ).fetchone()[0]

    groups_raw = conn.execute("""
        SELECT k.id, k.name, COUNT(l.id) as listing_count,
               MIN(l.price) as min_price, MAX(l.price) as max_price,
               MAX(l.found_at) as latest_found
        FROM keywords k JOIN listings l ON l.keyword_id = k.id
        WHERE COALESCE(l.hidden,0) = 0
        GROUP BY k.id ORDER BY MAX(l.found_at) DESC
    """).fetchall()

    groups = []
    for g in groups_raw:
        items = conn.execute(
            """
            SELECT * FROM listings WHERE keyword_id = ? AND COALESCE(hidden,0) = 0
            ORDER BY price ASC NULLS LAST
        """,
            (g["id"],),
        ).fetchall()
        groups.append(
            {
                "keyword_id": g["id"],
                "keyword": g["name"],
                "count": g["listing_count"],
                "min_price": g["min_price"],
                "max_price": g["max_price"],
                "latest_found": g["latest_found"],
                "listings": [
                    {**dict(i), "est_profit_jpy": dict(i).get("est_profit_jpy")}
                    for i in items
                ],
                "ebay_price": None,
                "ebay_qty": None,
                "ebay_listing_id": None,
                "ebay_title": None,
                "eship_profit": None,
            }
        )
    conn.close()

    # Enrich with eBay data from agent.db + eShip profit data
    db = get_db()
    try:
        ebay_listings = crud.get_all_listings(db)
        ebay_data = {}
        for row in ebay_listings:
            ebay_data[row.sku] = {
                "title": row.title,
                "title_lower": (row.title or "").lower(),
                "price_usd": row.price_usd,
                "quantity": row.quantity,
                "listing_id": row.listing_id,
                "sku": row.sku,
            }

        # Load eShip profit data from file cache (written by /deals/api/eship-sync)
        eship_profits = {}
        try:
            cache_file = os.path.join(
                os.path.dirname(DEAL_WATCHER_DB), ".eship_profit_cache.json"
            )
            if os.path.exists(cache_file):
                import json as _json

                with open(cache_file, "r") as f:
                    cache_data = _json.load(f)
                if time.time() - cache_data.get("ts", 0) < 3600:
                    eship_profits = cache_data.get("profits", {})
        except Exception as e:
            logger.warning(f"Could not load eShip profits: {e}")

        for group in groups:
            kw_lower = group["keyword"].lower()
            kw_words = kw_lower.split()
            best, best_score = None, 0
            for sku, info in ebay_data.items():
                if all(w in info["title_lower"] for w in kw_words):
                    score = len(kw_words)
                    if score > best_score:
                        best_score = score
                        best = info
            if best:
                group["ebay_price"] = best["price_usd"]
                group["ebay_qty"] = best["quantity"]
                group["ebay_listing_id"] = best["listing_id"]
                group["ebay_title"] = best["title"]
                group["ebay_sku"] = best["sku"]

                # eShip profit = 売上 - 手数料 - 送料 - 関税 - 広告費 - 仕入原価
                # Match by listing_id (Item ID) first, then SKU
                eship = eship_profits.get(best["listing_id"], {}) or eship_profits.get(
                    best["sku"], {}
                )
                base_profit = eship.get("profit")  # eShipの登録仕入価格ベースの利益
                eship_pp = eship.get("purchase_price")  # eShipの登録仕入価格

                # Per-listing profit: adjust by price difference
                # adjusted_profit = base_profit + (eship_purchase_price - listing_price)
                for item in group["listings"]:
                    cost_jpy = item.get("price") or 0
                    if (
                        base_profit is not None
                        and eship_pp is not None
                        and cost_jpy > 0
                    ):
                        adjusted = base_profit + (eship_pp - cost_jpy)
                        item["est_profit_jpy"] = round(adjusted)
                    else:
                        item["est_profit_jpy"] = None

                # Group-level: show best (cheapest listing) profit
                profits = [
                    i["est_profit_jpy"]
                    for i in group["listings"]
                    if i.get("est_profit_jpy") is not None
                ]
                group["eship_profit"] = max(profits) if profits else None
    finally:
        db.close()

    return {
        "groups": groups,
        "keywords": keywords,
        "kw_count": kw_count,
        "listing_count": listing_count,
        "hidden_count": hidden_count,
    }


@app.get("/deals", response_class=HTMLResponse)
async def deals_redirect():
    return RedirectResponse(url="/research?tab=deals", status_code=301)


@app.post("/deals/scan")
async def deals_scan():
    """Proxy scan trigger to deal-watcher service."""
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            await client.post("http://127.0.0.1:8001/scan", timeout=5)
    except Exception:
        pass
    return RedirectResponse("/deals", status_code=303)


@app.post("/deals/keywords/add")
async def deals_add_keyword(name: str = Form(...)):
    import sqlite3

    name = name.strip()
    if name:
        conn = sqlite3.connect(DEAL_WATCHER_DB)
        conn.execute("INSERT OR IGNORE INTO keywords (name) VALUES (?)", (name,))
        conn.commit()
        conn.close()
    return RedirectResponse("/deals", status_code=303)


@app.post("/deals/keywords/{keyword_id}/toggle")
async def deals_toggle_keyword(keyword_id: int):
    import sqlite3

    conn = sqlite3.connect(DEAL_WATCHER_DB)
    conn.execute("UPDATE keywords SET active = 1 - active WHERE id = ?", (keyword_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/deals", status_code=303)


@app.post("/deals/keywords/{keyword_id}/delete")
async def deals_delete_keyword(keyword_id: int):
    import sqlite3

    conn = sqlite3.connect(DEAL_WATCHER_DB)
    conn.execute("DELETE FROM keywords WHERE id = ?", (keyword_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/deals", status_code=303)


@app.post("/deals/listings/{listing_id}/hide")
async def deals_hide_listing(listing_id: int):
    import sqlite3

    conn = sqlite3.connect(DEAL_WATCHER_DB)
    conn.execute("UPDATE listings SET hidden = 1 WHERE id = ?", (listing_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/deals", status_code=303)


@app.post("/deals/keywords/{keyword_id}/hide-all")
async def deals_hide_keyword(keyword_id: int):
    import sqlite3

    conn = sqlite3.connect(DEAL_WATCHER_DB)
    conn.execute("UPDATE listings SET hidden = 1 WHERE keyword_id = ?", (keyword_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/deals", status_code=303)


@app.post("/deals/api/eship-sync")
async def deals_eship_sync():
    """Fetch eShip profit data for all inventory items (cached 1hr)."""
    import importlib

    dw_dir = os.path.dirname(DEAL_WATCHER_DB)
    if dw_dir not in sys.path:
        sys.path.insert(0, dw_dir)
    import eship as eship_mod

    importlib.reload(eship_mod)

    profits = await eship_mod.fetch_eship_profits()
    return JSONResponse({"status": "ok", "count": len(profits), "data": profits})


@app.post("/deals/api/eship")
async def deals_eship(
    listing_id: int = Form(...),
    ebay_title: str = Form(...),
):
    """Send a deal-watcher listing to eShip via browser automation."""
    import sqlite3
    import sys
    import os

    # Read listing from deal-watcher DB
    conn = sqlite3.connect(DEAL_WATCHER_DB)
    conn.row_factory = sqlite3.Row
    listing = conn.execute(
        "SELECT * FROM listings WHERE id = ?", (listing_id,)
    ).fetchone()
    conn.close()

    if not listing:
        return JSONResponse({"status": "error", "message": "Listing not found"})

    # Import eship module from deal-watcher (reload to pick up changes)
    import importlib

    dw_dir = os.path.dirname(DEAL_WATCHER_DB)
    if dw_dir not in sys.path:
        sys.path.insert(0, dw_dir)

    import eship

    importlib.reload(eship)
    update_eship_item = eship.update_eship_item

    # Look up SKU from Agent DB for more reliable eShip search
    sku = ""
    try:
        agent_db = os.path.join(os.path.dirname(__file__), "agent.db")
        aconn = sqlite3.connect(agent_db)
        aconn.row_factory = sqlite3.Row
        row = aconn.execute(
            "SELECT sku FROM listings WHERE title = ?", (ebay_title,)
        ).fetchone()
        if row:
            sku = row["sku"] or ""
        aconn.close()
    except Exception:
        pass

    result = await update_eship_item(
        ebay_title=ebay_title,
        supplier_url=listing["url"],
        purchase_price=listing["price"] or 0,
        platform=listing["platform"],
        set_quantity=1,
        sku=sku,
    )

    # On success, update eBay Agent DB quantity so Deal Watcher shows correct stock
    if result.get("status") == "ok":
        try:
            agent_db = os.path.join(os.path.dirname(__file__), "agent.db")
            agent_conn = sqlite3.connect(agent_db)
            agent_conn.execute(
                "UPDATE listings SET quantity = 1 WHERE title = ?", (ebay_title,)
            )
            agent_conn.commit()
            agent_conn.close()
            logger.info(f"Updated Agent DB quantity for: {ebay_title}")
        except Exception as e:
            logger.warning(f"Failed to update Agent DB: {e}")

    return JSONResponse(result)


# ── AIエージェント API ────────────────────────────────────


@app.post("/api/agent")
async def agent_endpoint(request: Request):
    """自然言語でAIエージェントに指示するエンドポイント"""
    body = await request.json()
    message = body.get("message", "")
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    try:
        result = await run_agent(message)
        return JSONResponse(result)
    except TypeError as e:
        if "api_key" in str(e):
            raise HTTPException(
                status_code=500,
                detail="ANTHROPIC_API_KEY が設定されていません。.env ファイルにキーを追加してください。",
            )
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("Agent error")
        raise HTTPException(status_code=500, detail=str(e))


# ── ツール直接呼び出し API ────────────────────────────────


@app.post("/api/tool/{tool_name}")
async def tool_endpoint(tool_name: str, request: Request):
    """個別ツールを直接呼び出すエンドポイント"""
    body = await request.json() if await request.body() else {}
    try:
        result = await handle_tool_call(tool_name, body)
        import json

        return JSONResponse(json.loads(result))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 出品管理 API ──────────────────────────────────────────


@app.get("/api/listings")
async def list_listings():
    db = get_db()
    try:
        listings = crud.get_all_listings(db)
        return [
            {
                "sku": l.sku,
                "title": l.title,
                "price_usd": l.price_usd,
                "quantity": l.quantity,
                "seo_score": l.seo_score,
                "category_name": l.category_name,
            }
            for l in listings
        ]
    finally:
        db.close()


@app.get("/api/listings/{sku}")
async def get_listing(sku: str):
    db = get_db()
    try:
        listing = crud.get_listing(db, sku)
        if not listing:
            raise HTTPException(status_code=404, detail=f"SKU {sku} not found")
        return {
            "sku": listing.sku,
            "listing_id": listing.listing_id,
            "title": listing.title,
            "description": listing.description,
            "price_usd": listing.price_usd,
            "quantity": listing.quantity,
            "category_name": listing.category_name,
            "condition": listing.condition,
            "seo_score": listing.seo_score,
        }
    finally:
        db.close()


# ── 出品生成 API ──────────────────────────────────────────


@app.post("/api/generate")
async def generate_listing_endpoint(request: Request):
    """AI出品生成"""
    body = await request.json()
    result = await handle_tool_call("generate_listing", body)
    import json

    return JSONResponse(json.loads(result))


# ── SEO分析 API ───────────────────────────────────────────


@app.post("/api/analyze/{sku}")
async def analyze_seo_endpoint(sku: str):
    result = await handle_tool_call("analyze_seo", {"sku": sku})
    import json

    return JSONResponse(json.loads(result))


# ── 為替レート API ────────────────────────────────────────


@app.get("/api/exchange-rate")
async def exchange_rate_endpoint():
    result = await handle_tool_call("get_exchange_rate", {})
    import json

    return JSONResponse(json.loads(result))


# ── 利益計算 API ──────────────────────────────────────────


@app.post("/api/margin")
async def margin_endpoint(request: Request):
    body = await request.json()
    result = await handle_tool_call("calculate_margin", body)
    import json

    return JSONResponse(json.loads(result))


# ── 売上分析 API ──────────────────────────────────────────


@app.get("/api/sales/summary")
async def sales_summary(days: int = 30):
    db = get_db()
    try:
        return crud.get_sales_summary(db, days=days)
    finally:
        db.close()


# ── 死に筒Refresh API（S2施策） ──────────────────────────


@app.get("/api/refresh/candidates")
async def refresh_candidates(limit: int = 50):
    """死に筒SKUの抽出プレビュー"""
    from listing.refresh import find_dead_listings

    db = get_db()
    try:
        listings = find_dead_listings(db, limit=limit)
        return {
            "count": len(listings),
            "items": [
                {
                    "sku": l.sku,
                    "title": l.title,
                    "price_usd": l.price_usd,
                    "listing_id": l.listing_id,
                }
                for l in listings
            ],
        }
    finally:
        db.close()


@app.post("/api/refresh/dry-run")
async def refresh_dry_run(request: Request):
    """サンプルSKUで新タイトル生成＋品質ガード結果を返す（eBay無変更）"""
    body = await request.json() if await request.body() else {}
    sample_size = int(body.get("sample_size", 10))
    from listing.refresh import dry_run_refresh

    db = get_db()
    try:
        results = await dry_run_refresh(db, sample_size=sample_size)
        passed = sum(1 for r in results if r.get("passed"))
        return {
            "total": len(results),
            "passed": passed,
            "pass_rate": round(passed / len(results), 3) if results else 0,
            "results": results,
        }
    finally:
        db.close()


@app.post("/api/refresh/run-slot")
async def refresh_run_slot(request: Request):
    """手動でスロットを1回実行（cron呼び出しと同じ処理）"""
    body = await request.json() if await request.body() else {}
    dry_run = bool(body.get("dry_run", False))
    daily_target = int(body.get("daily_target", 30))
    from listing.refresh import run_refresh_slot

    result = await run_refresh_slot(daily_target=daily_target, dry_run=dry_run)
    return result


@app.post("/api/refresh/revise")
async def refresh_revise(request: Request):
    """指定SKUを即Revise（テスト用・単発）"""
    body = await request.json()
    sku = body.get("sku", "")
    dry_run = bool(body.get("dry_run", False))
    if not sku:
        raise HTTPException(400, "sku required")
    from listing.refresh import refresh_single

    db = get_db()
    try:
        listing = db.get(Listing, sku)
        if not listing:
            raise HTTPException(404, f"SKU {sku} not found")
        return await refresh_single(db, listing, dry_run=dry_run)
    finally:
        db.close()


@app.get("/api/refresh/status")
async def refresh_status():
    """直近の実行状況サマリー"""
    from database.models import ListingRefreshBackup, ListingRefreshRun
    from datetime import datetime, timedelta

    db = get_db()
    try:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        runs = (
            db.query(ListingRefreshRun)
            .filter(ListingRefreshRun.scheduled_date == today)
            .all()
        )
        outcomes: dict = {}
        for r in runs:
            outcomes[r.outcome] = outcomes.get(r.outcome, 0) + 1
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent = (
            db.query(ListingRefreshBackup)
            .filter(ListingRefreshBackup.created_at >= week_ago)
            .all()
        )
        weekly_outcomes: dict = {}
        for b in recent:
            weekly_outcomes[b.status] = weekly_outcomes.get(b.status, 0) + 1
        return {
            "today_outcomes": outcomes,
            "today_total_runs": len(runs),
            "week_backup_status": weekly_outcomes,
            "enabled": os.getenv("LISTING_REFRESH_ENABLED", "false").lower() == "true",
        }
    finally:
        db.close()


@app.get("/api/refresh/backups")
async def refresh_backups(limit: int = 50, status: str = ""):
    """バックアップ一覧（ロールバック対象確認）"""
    from database.models import ListingRefreshBackup

    db = get_db()
    try:
        q = db.query(ListingRefreshBackup).order_by(
            ListingRefreshBackup.created_at.desc()
        )
        if status:
            q = q.filter(ListingRefreshBackup.status == status)
        items = q.limit(limit).all()
        return {
            "count": len(items),
            "items": [
                {
                    "id": b.id,
                    "sku": b.sku,
                    "status": b.status,
                    "old_title": b.old_title,
                    "new_title": b.new_title,
                    "old_price": b.old_price_usd,
                    "new_price": b.new_price_usd,
                    "applied_at": b.applied_at.isoformat() if b.applied_at else None,
                    "error": b.error_message,
                }
                for b in items
            ],
        }
    finally:
        db.close()


@app.post("/api/refresh/rollback/{backup_id}")
async def refresh_rollback(backup_id: int):
    """指定バックアップIDの変更を元に戻す"""
    from listing.refresh import rollback

    db = get_db()
    try:
        return rollback(db, backup_id)
    finally:
        db.close()


# ── Phase 2: 価格インテリジェンス API ─────────────────────
# 注意: 固定パスルートを {sku} パラメータルートより先に定義


@app.post("/api/pricing/monitor")
async def run_monitor(request: Request):
    """競合価格一括チェック"""
    body = await request.json() if await request.body() else {}
    result = await handle_tool_call("run_price_monitor", body)
    return JSONResponse(json.loads(result))


@app.post("/api/pricing/batch-advice")
async def batch_advice(request: Request):
    """一括AI価格提案"""
    body = await request.json() if await request.body() else {}
    result = await handle_tool_call("batch_price_advice", body)
    return JSONResponse(json.loads(result))


@app.post("/api/pricing/apply")
async def apply_price(request: Request):
    """価格変更をeBayに適用"""
    body = await request.json()
    result = await handle_tool_call("apply_price_change", body)
    return JSONResponse(json.loads(result))


@app.get("/api/pricing/alerts")
async def price_alerts():
    """価格アラート（差が大きい出品）を取得"""
    db = get_db()
    try:
        from sqlalchemy import func
        from database.models import PriceHistory

        # SKU毎に最新レコードを取得
        subq = (
            db.query(
                PriceHistory.sku,
                func.max(PriceHistory.id).label("max_id"),
            )
            .group_by(PriceHistory.sku)
            .subquery()
        )

        latest = (
            db.query(PriceHistory).join(subq, PriceHistory.id == subq.c.max_id).all()
        )

        alerts = []
        for ph in latest:
            if ph.avg_competitor_price_usd > 0:
                diff = (
                    (ph.our_price_usd - ph.avg_competitor_price_usd)
                    / ph.avg_competitor_price_usd
                    * 100
                )
                if abs(diff) > 10:
                    listing = crud.get_listing(db, ph.sku)
                    alerts.append(
                        {
                            "sku": ph.sku,
                            "title": listing.title if listing else ph.sku,
                            "our_price": ph.our_price_usd,
                            "avg_competitor": ph.avg_competitor_price_usd,
                            "lowest_competitor": ph.lowest_competitor_price_usd,
                            "diff_pct": round(diff, 1),
                            "action": "値下げ検討" if diff > 10 else "値上げ余地あり",
                            "recorded_at": ph.recorded_at.isoformat(),
                        }
                    )

        alerts.sort(key=lambda a: abs(a["diff_pct"]), reverse=True)
        return alerts
    finally:
        db.close()


# ── 価格分析（SKUパラメータルート — 固定パスルートより後に定義） ──


@app.post("/api/pricing/advice/{sku}")
async def price_advice(sku: str, request: Request):
    """AI価格アドバイス"""
    body = await request.json() if await request.body() else {}
    body["sku"] = sku
    result = await handle_tool_call("get_price_advice", body)
    return JSONResponse(json.loads(result))


@app.get("/api/pricing/history/{sku}")
async def price_history(sku: str, days: int = 30):
    """価格履歴を取得"""
    db = get_db()
    try:
        history = crud.get_price_history(db, sku, days=days)
        return [
            {
                "recorded_at": h.recorded_at.isoformat(),
                "our_price": h.our_price_usd,
                "avg_competitor": h.avg_competitor_price_usd,
                "lowest_competitor": h.lowest_competitor_price_usd,
                "num_competitors": h.num_competitors,
                "exchange_rate": h.exchange_rate,
            }
            for h in history
        ]
    finally:
        db.close()


@app.post("/api/pricing/{sku}")
async def pricing_endpoint(sku: str):
    """競合価格分析（単体SKU）"""
    result = await handle_tool_call("analyze_pricing", {"sku": sku})
    import json

    return JSONResponse(json.loads(result))


# ── Phase 3: 需要検知・リサーチ API ────────────────────────


@app.post("/api/research/demand")
async def research_demand_endpoint(request: Request):
    """市場需要分析"""
    body = await request.json()
    result = await handle_tool_call("research_demand", body)
    return JSONResponse(json.loads(result))


@app.post("/api/research/compare")
async def compare_categories_endpoint(request: Request):
    """カテゴリ比較分析"""
    body = await request.json()
    result = await handle_tool_call("compare_categories", body)
    return JSONResponse(json.loads(result))


@app.post("/api/research/agent")
async def research_agent_endpoint(request: Request):
    """AIリサーチエージェント"""
    body = await request.json()
    result = await handle_tool_call("run_research", body)
    return JSONResponse(json.loads(result))


@app.post("/api/pipeline/preview")
async def pipeline_preview_endpoint(request: Request):
    """出品パイプライン — ドラフト生成"""
    body = await request.json()
    result = await handle_tool_call("generate_and_preview", body)
    return JSONResponse(json.loads(result))


# ── Phase 4: コミュニケーション＆分析 API ──────────────────


@app.post("/api/sales/sync")
async def sync_sales_endpoint(request: Request):
    """売上データ同期"""
    body = await request.json() if await request.body() else {}
    result = await handle_tool_call("sync_sales", body)
    return JSONResponse(json.loads(result))


@app.get("/api/sales/analytics")
async def sales_analytics_endpoint(
    days: int = 30, start_date: str = "", end_date: str = ""
):
    """売上分析レポート"""
    params = {"days": days}
    if start_date and end_date:
        params["start_date"] = start_date
        params["end_date"] = end_date
    result = await handle_tool_call("get_sales_analytics", params)
    return JSONResponse(json.loads(result))


@app.get("/api/messages")
async def messages_endpoint(days: int = 7):
    """バイヤーメッセージ一覧"""
    result = await handle_tool_call("check_messages", {"days": days})
    return JSONResponse(json.loads(result))


@app.post("/api/messages/draft")
async def draft_reply_endpoint(request: Request):
    """返信ドラフト生成"""
    body = await request.json()
    result = await handle_tool_call("draft_reply", body)
    return JSONResponse(json.loads(result))


@app.post("/api/messages/process")
async def process_messages_endpoint(request: Request):
    """未読メッセージ一括処理"""
    body = await request.json() if await request.body() else {}
    result = await handle_tool_call("process_unread_messages", body)
    return JSONResponse(json.loads(result))


# ── アクティビティ API ──────────────────────────────────


@app.get("/api/activity/recent")
async def recent_activity(limit: int = 10):
    """最近のアクティビティ"""
    from database.models import SalesRecord, ChangeHistory
    from sqlalchemy import desc

    db = get_db()
    try:
        sales = (
            db.query(SalesRecord).order_by(desc(SalesRecord.sold_at)).limit(limit).all()
        )
        changes = (
            db.query(ChangeHistory)
            .order_by(desc(ChangeHistory.applied_at))
            .limit(limit)
            .all()
        )
        activities = []
        for s in sales:
            activities.append(
                {
                    "type": "sale",
                    "time": s.sold_at.isoformat(),
                    "text": f"Sale: {s.title[:40]} ${s.sale_price_usd:.2f}",
                }
            )
        for c in changes:
            activities.append(
                {
                    "type": "change",
                    "time": c.applied_at.isoformat(),
                    "text": f"Changed: {c.sku[:20]} {c.field_changed}",
                }
            )
        activities.sort(key=lambda a: a["time"], reverse=True)
        return activities[:limit]
    finally:
        db.close()


# ── 仕入れ管理 API ──────────────────────────────────────


@app.get("/api/procurements")
async def list_procurements(status: str = ""):
    """仕入れ実績一覧（売上紐付け情報付き）"""
    db = get_db()
    try:
        procs = crud.get_all_procurements(db, status=status)

        # order_id → 売上情報マップ（FIFO/明示紐付け済みのみ）
        all_sales = db.query(crud.SalesRecord).all()
        sales_by_order_id: dict = {}
        for s in all_sales:
            if s.order_id and s.order_id not in sales_by_order_id:
                sales_by_order_id[s.order_id] = {
                    "sold": True,
                    "sale_price_usd": s.sale_price_usd,
                    "net_profit_jpy": s.net_profit_jpy,
                    "consumption_tax_jpy": s.consumption_tax_jpy,
                    "sold_at": s.sold_at.isoformat() if s.sold_at else None,
                    "buyer_name": s.buyer_name,
                    "order_id": s.order_id,
                }

        # SKU→画像URLマップ
        skus = list({p.sku for p in procs if p.sku})
        image_map = {}
        if skus:
            listings = (
                db.query(Listing.sku, Listing.image_urls_json)
                .filter(Listing.sku.in_(skus))
                .all()
            )
            for l in listings:
                try:
                    urls = json.loads(l.image_urls_json) if l.image_urls_json else []
                    if urls:
                        image_map[l.sku] = urls[0]
                except (json.JSONDecodeError, IndexError):
                    pass

        result = []
        for p in procs:
            item = {
                "id": p.id,
                "sku": p.sku,
                "platform": p.platform,
                "title": p.title,
                "url": p.url or "",
                "image_url": p.image_url or image_map.get(p.sku, ""),
                "purchase_price_jpy": p.purchase_price_jpy,
                "shipping_cost_jpy": p.shipping_cost_jpy,
                "other_cost_jpy": p.other_cost_jpy,
                "consumption_tax_jpy": p.consumption_tax_jpy,
                "total_cost_jpy": p.total_cost_jpy,
                "status": p.status,
                "purchase_date": p.purchase_date.isoformat()
                if p.purchase_date
                else None,
                "received_date": p.received_date.isoformat()
                if p.received_date
                else None,
                "notes": p.notes or "",
                "quantity": p.quantity,
                "seller_id": p.seller_id,
                "seller_url": p.seller_url,
                "screenshot_path": p.screenshot_path,
                "category": p.category,
                "condition": p.condition,
                "stock_number": p.stock_number,
                "location": p.location,
                "ebay_item_id": p.ebay_item_id,
                "ebay_order_id": p.ebay_order_id,
                "ebay_price_usd": p.ebay_price_usd,
                "listed_at": p.listed_at.isoformat() if p.listed_at else None,
                "sold_at": p.sold_at.isoformat() if p.sold_at else None,
                "shipped_at": p.shipped_at.isoformat() if p.shipped_at else None,
                "sale": sales_by_order_id.get(p.ebay_order_id),
                "domestic_platform": p.domestic_platform or "",
                "domestic_sale_price_jpy": p.domestic_sale_price_jpy or 0,
                "domestic_sale_date": p.domestic_sale_date.isoformat()
                if p.domestic_sale_date
                else None,
                "domestic_reason": p.domestic_reason or "",
                "transaction_id": p.transaction_id or "",
            }
            result.append(item)
        return result
    finally:
        db.close()


@app.get("/api/procurements/domestic-sales")
async def list_domestic_sales(month: str = ""):
    """国内販売（sold_domestic）の一覧と集計 — 利益ページ用"""
    db = get_db()
    try:
        q = db.query(Procurement).filter(
            Procurement.status == "sold_domestic",
            Procurement.domestic_sale_price_jpy > 0,
        )
        if month:
            # YYYY-MM フィルタ
            try:
                from sqlalchemy import func as _func

                q = q.filter(
                    _func.strftime("%Y-%m", Procurement.domestic_sale_date) == month
                )
            except Exception:
                pass
        procs = q.order_by(Procurement.domestic_sale_date.desc()).all()
        items = []
        for p in procs:
            cost = p.total_cost_jpy or (
                p.purchase_price_jpy
                + p.shipping_cost_jpy
                + (p.consumption_tax_jpy or 0)
            )
            profit = p.domestic_sale_price_jpy - cost
            items.append(
                {
                    "id": p.id,
                    "stock_number": p.stock_number or "",
                    "title": p.title or "",
                    "platform": p.domestic_platform or "",
                    "sale_date": p.domestic_sale_date.strftime("%Y-%m-%d")
                    if p.domestic_sale_date
                    else "",
                    "sale_price_jpy": p.domestic_sale_price_jpy,
                    "total_cost_jpy": cost,
                    "consumption_tax_jpy": p.consumption_tax_jpy or 0,
                    "net_profit_jpy": profit,
                    "reason": p.domestic_reason or "",
                    "sku": p.sku or "",
                }
            )
        total_revenue = sum(x["sale_price_jpy"] for x in items)
        total_cost = sum(x["total_cost_jpy"] for x in items)
        total_profit = sum(x["net_profit_jpy"] for x in items)
        total_tax = sum(x["consumption_tax_jpy"] for x in items)
        return {
            "items": items,
            "summary": {
                "count": len(items),
                "revenue_jpy": total_revenue,
                "cost_jpy": total_cost,
                "net_profit_jpy": total_profit,
                "consumption_tax_jpy": total_tax,
            },
        }
    finally:
        db.close()


@app.get("/api/procurements/stats")
async def procurement_stats():
    """仕入れ記録KPI統計"""
    db = get_db()
    try:
        return JSONResponse(crud.get_procurement_stats(db))
    finally:
        db.close()


@app.post("/api/procurements/auto-sku")
async def proc_auto_sku():
    """SKUなしの仕入れ記録にeBay出品とのマッチングでSKU/eBay IDを自動付与"""
    import re

    def extract_models(title: str) -> list:
        models = []
        brand_pats = re.findall(
            r"(?:TASCAM|YAMAHA|SONY|DENON|PIONEER|ROLAND|BOSS|KORG|TECHNICS|CASIO|TEAC|ZOOM|AKAI|NAKAMICHI|ACCUPHASE|LUXMAN|MARANTZ|SANSUI|ONKYO|JBL|BOSE|SHURE)"
            r"\s+([A-Za-z0-9][\w\-]+)",
            title,
            re.IGNORECASE,
        )
        for m in brand_pats:
            if len(m) >= 3:
                models.append(m)
        hyphen = re.findall(
            r"[A-Za-z]{1,10}[\-][A-Za-z0-9]{1,10}(?:[\-][A-Za-z0-9]+)*", title
        )
        for m in hyphen:
            if len(m) >= 4 and m not in models:
                models.append(m)
        alnum = re.findall(r"[A-Za-z]{1,6}\d{2,5}[A-Za-z]*", title)
        for m in alnum:
            if len(m) >= 4 and m not in models:
                models.append(m)
        numalpha = re.findall(r"\d{3,5}[A-Za-z]{2,}", title)
        for m in numalpha:
            if len(m) >= 4 and m not in models:
                models.append(m)
        junk = {"JUNK", "CD-ROM", "USB-", "OK", "ver", "No"}
        models = [
            m
            for m in models
            if m not in junk and not m.startswith("N1") and not m.startswith("w2")
        ]
        return models

    db = get_db()
    try:
        procs = (
            db.query(Procurement)
            .filter((Procurement.sku == "") | (Procurement.sku == None))
            .all()
        )
        listings = db.query(Listing).all()
        listing_map = [
            (l.sku, l.title.lower(), l.listing_id, l.price_usd) for l in listings
        ]

        assigned = 0
        skipped = 0
        results = []
        for proc in procs:
            models = extract_models(proc.title)
            if not models:
                skipped += 1
                continue
            best = None
            best_len = 0
            for model in models:
                ml = model.lower()
                if len(ml) < 4:
                    continue
                for sku, lt, listing_id, price_usd in listing_map:
                    if ml in lt:
                        if len(ml) > best_len:
                            best = (sku, listing_id, price_usd, model)
                            best_len = len(ml)
                        break
            if best:
                proc.sku = best[0]
                # ebay_item_id / ebay_price_usd はタイトルマッチでは設定しない
                # （誤った過去ItemIDの紐付けを防ぐ）
                assigned += 1
                results.append(
                    {
                        "id": proc.id,
                        "title": proc.title[:50],
                        "matched_model": best[3],
                        "sku": best[0],
                    }
                )
            else:
                skipped += 1
        db.commit()
        return JSONResponse(
            {
                "assigned": assigned,
                "skipped": skipped,
                "total": len(procs),
                "matches": results[:20],
            }
        )
    finally:
        db.close()


@app.post("/api/procurements")
async def create_procurement(request: Request):
    """仕入れ実績を記録"""
    body = await request.json()
    db = get_db()
    try:
        purchase_date = None
        if body.get("purchase_date"):
            try:
                purchase_date = datetime.strptime(body["purchase_date"], "%Y-%m-%d")
            except ValueError:
                pass
        try:
            _ebay_price_usd = float(body.get("ebay_price_usd", 0) or 0)
        except (TypeError, ValueError):
            _ebay_price_usd = 0.0
        proc = crud.add_procurement(
            db,
            sku=body.get("sku", ""),
            platform=body.get("platform", ""),
            title=body.get("title", ""),
            url=body.get("url", ""),
            purchase_price_jpy=int(body.get("purchase_price_jpy", 0)),
            shipping_cost_jpy=int(body.get("shipping_cost_jpy", 0)),
            other_cost_jpy=int(body.get("other_cost_jpy", 0)),
            consumption_tax_jpy=int(body.get("consumption_tax_jpy", 0)),
            notes=body.get("notes", ""),
            quantity=int(body.get("quantity", 1) or 1),
            seller_id=body.get("seller_id", ""),
            seller_url=body.get("seller_url", ""),
            screenshot_path=body.get("screenshot_path", ""),
            category=body.get("category", ""),
            image_url=body.get("image_url", ""),
            condition=body.get("condition", ""),
            stock_number=body.get("stock_number", ""),
            location=body.get("location", ""),
            ebay_item_id=body.get("ebay_item_id", ""),
            ebay_order_id=body.get("ebay_order_id", ""),
            ebay_price_usd=_ebay_price_usd,
            **({"purchase_date": purchase_date} if purchase_date else {}),
        )
        return JSONResponse(
            {
                "id": proc.id,
                "total_cost_jpy": proc.total_cost_jpy,
                "status": proc.status,
            }
        )
    finally:
        db.close()


@app.get("/api/procurements/export/ledger")
async def export_procurement_ledger():
    """古物商台帳 CSV エクスポート（古物営業法 施行規則第17条対応）"""
    import csv
    import io
    from fastapi.responses import StreamingResponse

    db = get_db()
    try:
        procs = crud.get_all_procurements(db)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "取引年月日",
                "品名",
                "数量",
                "取得価格(円)",
                "古物区分",
                "仕入先",
                "取引番号/注文番号",
                "仕入先URL",
                "出品者ID",
                "出品者URL",
                "取引証跡パス",
                "管理番号",
            ]
        )
        for p in procs:
            writer.writerow(
                [
                    p.purchase_date.strftime("%Y-%m-%d") if p.purchase_date else "",
                    p.title,
                    p.quantity,
                    p.purchase_price_jpy,
                    p.category,
                    p.platform,
                    p.transaction_id or "",
                    p.url or "",
                    p.seller_id or "",
                    p.seller_url or "",
                    p.screenshot_path or "",
                    p.stock_number or "",
                ]
            )
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue().encode("utf-8-sig")]),
            media_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="kojyo-ledger.csv"',
            },
        )
    finally:
        db.close()


@app.get("/api/procurements/missing-screenshots")
async def list_missing_screenshots(request: Request):
    """SSがない・URLありのレコード一覧（補完用）"""
    _auth_local_import(request)
    db = get_db()
    try:
        from sqlalchemy import or_

        rows = (
            db.query(Procurement)
            .filter(
                or_(
                    Procurement.screenshot_path == "",
                    Procurement.screenshot_path == None,
                ),
                Procurement.url != "",
                Procurement.url != None,
            )
            .order_by(Procurement.id)
            .all()
        )
        return JSONResponse(
            [
                {"id": r.id, "url": r.url, "platform": r.platform, "title": r.title}
                for r in rows
            ]
        )
    finally:
        db.close()


@app.get("/api/procurements/gdrive-screenshots")
async def list_gdrive_screenshots(request: Request):
    """GoogleドライブパスのSSレコード一覧（VPS移行用）"""
    _auth_local_import(request)
    db = get_db()
    try:
        rows = (
            db.query(Procurement)
            .filter(Procurement.screenshot_path.like("/Users/%/GoogleDrive%"))
            .order_by(Procurement.id)
            .all()
        )
        return JSONResponse(
            [
                {
                    "id": r.id,
                    "screenshot_path": r.screenshot_path,
                    "platform": r.platform,
                    "title": r.title,
                    "purchase_date": r.purchase_date.isoformat()
                    if r.purchase_date
                    else None,
                }
                for r in rows
            ]
        )
    finally:
        db.close()


@app.post("/api/procurements/{proc_id}/update-screenshot-path")
async def update_screenshot_path(proc_id: int, request: Request):
    """SSパスをVPSパスに更新（GDrive移行用）"""
    _auth_local_import(request)
    db = get_db()
    try:
        proc = db.query(Procurement).filter(Procurement.id == proc_id).first()
        if not proc:
            raise HTTPException(404, "Procurement not found")
        body = await request.json()
        new_path = body.get("screenshot_path", "")
        if not new_path:
            raise HTTPException(400, "screenshot_path is required")
        proc.screenshot_path = new_path
        db.commit()
        return JSONResponse({"status": "updated", "path": new_path})
    finally:
        db.close()


@app.get("/api/procurements/{sku}")
async def get_procurements_by_sku(sku: str):
    """SKU別仕入れ実績"""
    db = get_db()
    try:
        procs = crud.get_procurement_by_sku(db, sku)
        return [
            {
                "id": p.id,
                "sku": p.sku,
                "platform": p.platform,
                "title": p.title,
                "url": p.url,
                "purchase_price_jpy": p.purchase_price_jpy,
                "shipping_cost_jpy": p.shipping_cost_jpy,
                "other_cost_jpy": p.other_cost_jpy,
                "total_cost_jpy": p.total_cost_jpy,
                "status": p.status,
                "purchase_date": p.purchase_date.isoformat()
                if p.purchase_date
                else None,
                "received_date": p.received_date.isoformat()
                if p.received_date
                else None,
                "notes": p.notes,
            }
            for p in procs
        ]
    finally:
        db.close()


@app.put("/api/procurements/{proc_id}")
async def update_procurement_endpoint(proc_id: int, request: Request):
    """仕入れ実績を更新"""
    body = await request.json()
    kwargs = {}
    for key in [
        "sku",
        "platform",
        "title",
        "url",
        "status",
        "notes",
        "seller_id",
        "seller_url",
        "screenshot_path",
        "category",
        "image_url",
        "condition",
        "stock_number",
        "location",
        "ebay_item_id",
        "ebay_order_id",
        "domestic_platform",
        "domestic_reason",
        "transaction_id",
    ]:
        if key in body:
            kwargs[key] = body[key]
    for key in [
        "purchase_price_jpy",
        "shipping_cost_jpy",
        "other_cost_jpy",
        "consumption_tax_jpy",
        "quantity",
        "domestic_sale_price_jpy",
    ]:
        if key in body:
            try:
                kwargs[key] = int(body[key])
            except (TypeError, ValueError):
                pass
    if "ebay_price_usd" in body:
        try:
            kwargs["ebay_price_usd"] = float(body["ebay_price_usd"])
        except (TypeError, ValueError):
            pass
    if body.get("purchase_date"):
        try:
            kwargs["purchase_date"] = datetime.strptime(
                body["purchase_date"], "%Y-%m-%d"
            )
        except ValueError:
            pass
    if body.get("received_date"):
        try:
            kwargs["received_date"] = datetime.strptime(
                body["received_date"], "%Y-%m-%d"
            )
        except ValueError:
            pass
    if body.get("domestic_sale_date"):
        try:
            kwargs["domestic_sale_date"] = datetime.strptime(
                body["domestic_sale_date"], "%Y-%m-%d"
            )
        except ValueError:
            pass
    db = get_db()
    try:
        proc = crud.update_procurement(db, proc_id, **kwargs)
        if not proc:
            raise HTTPException(404, "Procurement not found")

        # ebay_order_id が設定された場合、対応するSalesRecordのコストを自動同期
        if kwargs.get("ebay_order_id"):
            from database.models import SalesRecord as _SR

            sale = db.query(_SR).filter(_SR.order_id == proc.ebay_order_id).first()
            if sale and (
                sale.source_cost_jpy != proc.purchase_price_jpy
                or sale.shipping_cost_jpy != proc.shipping_cost_jpy
                or sale.consumption_tax_jpy != proc.consumption_tax_jpy
            ):
                crud.update_sales_record(
                    db,
                    sale.id,
                    source_cost_jpy=proc.purchase_price_jpy,
                    shipping_cost_jpy=proc.shipping_cost_jpy,
                    consumption_tax_jpy=proc.consumption_tax_jpy,
                )

        return JSONResponse(
            {
                "id": proc.id,
                "status": proc.status,
                "total_cost_jpy": proc.total_cost_jpy,
            }
        )
    finally:
        db.close()


@app.delete("/api/procurements/{proc_id}")
async def delete_procurement(proc_id: int):
    """仕入れ実績を削除"""
    db = get_db()
    try:
        from database.models import Procurement

        proc = db.query(Procurement).filter(Procurement.id == proc_id).first()
        if not proc:
            raise HTTPException(404, "Procurement not found")
        db.delete(proc)
        db.commit()
        return JSONResponse({"status": "ok", "deleted": proc_id})
    finally:
        db.close()


@app.post("/api/procurements/bulk-delete-ids")
async def bulk_delete_procurements(request: Request):
    """IDリストで仕入れ記録を一括削除"""
    body = await request.json()
    ids = body.get("ids", [])
    if not ids:
        raise HTTPException(400, "ids must not be empty")
    db = get_db()
    try:
        count = (
            db.query(Procurement)
            .filter(Procurement.id.in_(ids))
            .delete(synchronize_session="fetch")
        )
        db.commit()
        return JSONResponse({"status": "deleted", "count": count})
    finally:
        db.close()


@app.post("/api/procurements/bulk-import")
async def bulk_import_procurements(request: Request):
    """購入履歴テキストから仕入れ記録を一括登録。
    rows: [{title, price, date, source, url, condition, seller, notes, tax, shipping}, ...]
    """
    body = await request.json()
    rows = body.get("rows", [])
    platform = body.get("platform", "")
    if not rows:
        return JSONResponse({"error": "rows is empty"}, status_code=400)

    db = get_db()
    try:
        created = 0
        skipped = 0
        for row in rows:
            title = (row.get("title") or "").strip()
            if not title:
                skipped += 1
                continue
            price = int(row.get("price", 0) or 0)
            source = row.get("source") or platform or ""
            existing = (
                db.query(Procurement)
                .filter(
                    Procurement.title == title,
                    Procurement.purchase_price_jpy == price,
                    Procurement.platform == source,
                )
                .first()
            )
            if existing:
                skipped += 1
                continue
            kwargs = {
                "title": title,
                "purchase_price_jpy": price,
                "consumption_tax_jpy": int(row.get("tax", 0) or 0),
                "shipping_cost_jpy": int(row.get("shipping", 0) or 0),
                "platform": source,
                "url": row.get("url", ""),
                "seller_id": row.get("seller", ""),
                "condition": row.get("condition", ""),
                "status": "purchased",
                "notes": row.get("notes", ""),
                "image_url": row.get("image_url", ""),
            }
            if row.get("date"):
                try:
                    kwargs["purchase_date"] = datetime.strptime(row["date"], "%Y-%m-%d")
                except ValueError:
                    pass
            crud.add_procurement(db, **kwargs)
            created += 1
        return JSONResponse(
            {
                "status": "imported",
                "created": created,
                "skipped": skipped,
                "total": len(rows),
            }
        )
    finally:
        db.close()


@app.post("/api/procurements/scrape/mercari")
async def proc_start_mercari_scrape():
    """メルカリ購入履歴をスクレイプして仕入れ記録に取り込む"""
    import uuid

    job_id = str(uuid.uuid4())[:8]
    _scrape_jobs[job_id] = {
        "status": "running",
        "message": "初期化中...",
        "current": 0,
        "total": 0,
        "results": [],
        "error": None,
    }

    async def run_scrape():
        from scrapers.mercari import scrape_mercari_purchases

        job = _scrape_jobs[job_id]
        try:

            def on_progress(msg, cur, total):
                job["message"] = msg
                job["current"] = cur
                job["total"] = total

            results = await scrape_mercari_purchases(
                on_progress=on_progress, headless=SCRAPER_HEADLESS
            )
            job["results"] = results
            job["status"] = "done"
            job["message"] = f"完了: {len(results)}件取得"
        except RuntimeError as e:
            if str(e) == "LOGIN_REQUIRED":
                job["status"] = "login_required"
                job["message"] = (
                    "メルカリログインが必要です。ローカルで再ログイン→同期してください。"
                )
                _notify_login_required("mercari", "メルカリ")
            else:
                job["status"] = "error"
                job["error"] = str(e)
                job["message"] = f"エラー: {e}"
        except Exception as e:
            job["status"] = "error"
            job["error"] = str(e)
            job["message"] = f"エラー: {e}"

    asyncio.create_task(run_scrape())
    return JSONResponse({"job_id": job_id, "status": "started"})


@app.post("/api/procurements/scrape/mercari/import/{job_id}")
async def proc_import_mercari_results(job_id: str):
    """メルカリスクレイプ結果を仕入れ記録に保存"""
    job = _scrape_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "done":
        raise HTTPException(400, f"Job not ready: {job['status']}")
    results = sorted(job.get("results", []), key=lambda r: r.get("date", "") or "9999")
    db = get_db()
    try:
        created = 0
        skipped = 0
        for row in results:
            title = (row.get("title") or "").strip()
            if not title:
                skipped += 1
                continue
            price = int(row.get("price", 0) or 0)
            existing = (
                db.query(Procurement)
                .filter(
                    Procurement.title == title,
                    Procurement.purchase_price_jpy == price,
                    Procurement.platform == "メルカリ",
                )
                .first()
            )
            if existing:
                skipped += 1
                continue
            kwargs = {
                "title": title,
                "purchase_price_jpy": price,
                "shipping_cost_jpy": int(row.get("shipping", 0) or 0),
                "platform": "メルカリ",
                "url": row.get("item_url", "") or row.get("transaction_url", ""),
                "image_url": row.get("image_url", ""),
                "screenshot_path": row.get("screenshot_path", ""),
                "status": "purchased",
            }
            if row.get("date"):
                try:
                    kwargs["purchase_date"] = datetime.strptime(row["date"], "%Y-%m-%d")
                except ValueError:
                    pass
            crud.add_procurement(db, **kwargs)
            created += 1
        _scrape_jobs.pop(job_id, None)
        return JSONResponse(
            {
                "status": "imported",
                "created": created,
                "skipped": skipped,
                "total": len(results),
            }
        )
    finally:
        db.close()


@app.post("/api/procurements/scrape/yahoo")
async def proc_start_yahoo_scrape(request: Request):
    """ヤフオク落札一覧をスクレイプして仕入れ記録に取り込む"""
    import uuid

    try:
        body = await request.json()
    except Exception:
        body = {}
    max_pages = int(body.get("max_pages", 50))
    job_id = str(uuid.uuid4())[:8]
    _scrape_jobs[job_id] = {
        "status": "running",
        "message": "初期化中...",
        "current": 0,
        "total": 0,
        "results": [],
        "error": None,
    }

    async def run_scrape():
        from scrapers.yahoo_auctions import scrape_yahoo_won

        job = _scrape_jobs[job_id]
        try:

            def on_progress(msg, cur, total):
                job["message"] = msg
                job["current"] = cur
                job["total"] = total

            results = await scrape_yahoo_won(
                on_progress=on_progress, max_pages=max_pages, headless=SCRAPER_HEADLESS
            )
            job["results"] = results
            job["status"] = "done"
            job["message"] = f"完了: {len(results)}件取得"
        except RuntimeError as e:
            if str(e) == "LOGIN_REQUIRED":
                job["status"] = "login_required"
                job["message"] = (
                    "Yahooログインが必要です。ローカルで再ログイン→同期してください。"
                )
                _notify_login_required("yahoo", "Yahoo!オークション")
            else:
                job["status"] = "error"
                job["error"] = str(e)
                job["message"] = f"エラー: {e}"
        except Exception as e:
            job["status"] = "error"
            job["error"] = str(e)
            job["message"] = f"エラー: {e}"

    asyncio.create_task(run_scrape())
    return JSONResponse({"job_id": job_id, "status": "started"})


@app.post("/api/procurements/scrape/yahoo/import/{job_id}")
async def proc_import_yahoo_results(job_id: str):
    """ヤフオクスクレイプ結果を仕入れ記録に保存"""
    job = _scrape_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "done":
        raise HTTPException(400, f"Job not ready: {job['status']}")
    results = sorted(job.get("results", []), key=lambda r: r.get("date", "") or "9999")
    db = get_db()
    try:
        created = 0
        skipped = 0
        for row in results:
            title = (row.get("title") or "").strip()
            if not title:
                skipped += 1
                continue
            price = int(row.get("price", 0) or 0)
            existing = (
                db.query(Procurement)
                .filter(
                    Procurement.title == title,
                    Procurement.purchase_price_jpy == price,
                    Procurement.platform == "ヤフオク",
                )
                .first()
            )
            if existing:
                skipped += 1
                continue
            kwargs = {
                "title": title,
                "purchase_price_jpy": price,
                "platform": "ヤフオク",
                "url": row.get("item_url", "") or row.get("url", ""),
                "seller_id": row.get("seller_id", "") or row.get("seller", ""),
                "image_url": row.get("image_url", ""),
                "screenshot_path": row.get("screenshot_path", ""),
                "status": "purchased",
            }
            if row.get("date"):
                try:
                    kwargs["purchase_date"] = datetime.strptime(row["date"], "%Y-%m-%d")
                except ValueError:
                    pass
            crud.add_procurement(db, **kwargs)
            created += 1
        _scrape_jobs.pop(job_id, None)
        return JSONResponse(
            {
                "status": "imported",
                "created": created,
                "skipped": skipped,
                "total": len(results),
            }
        )
    finally:
        db.close()


@app.post("/api/procurements/fifo-assign")
async def fifo_assign_procurements(request: Request):
    """同一 eBay Item ID の仕入れ記録を売上と購入日順に FIFO 自動紐付け"""
    body = await request.json()
    ebay_item_id = (body.get("ebay_item_id") or "").strip()
    if not ebay_item_id:
        raise HTTPException(400, "ebay_item_id required")

    db = get_db()
    try:
        from database.models import SalesRecord

        # 未紐付け仕入れ（purchase_date 昇順）
        procs = (
            db.query(Procurement)
            .filter(
                Procurement.ebay_item_id == ebay_item_id,
                (Procurement.ebay_order_id == "") | (Procurement.ebay_order_id == None),
            )
            .order_by(Procurement.purchase_date.asc())
            .all()
        )

        # 既紐付け済み order_id を収集
        linked_ids = {
            p.ebay_order_id
            for p in db.query(Procurement)
            .filter(
                Procurement.ebay_item_id == ebay_item_id,
                Procurement.ebay_order_id != "",
            )
            .all()
            if p.ebay_order_id
        }

        # 対応する売上（sold_at 昇順、未紐付けのみ）
        all_sales = (
            db.query(SalesRecord)
            .filter(SalesRecord.item_id == ebay_item_id)
            .order_by(SalesRecord.sold_at.asc())
            .all()
        )
        unlinked_sales = [s for s in all_sales if s.order_id not in linked_ids]

        assigned = []
        for proc, sale in zip(procs, unlinked_sales):
            proc.ebay_order_id = sale.order_id
            assigned.append(
                {
                    "procurement_id": proc.id,
                    "title": proc.title[:40],
                    "order_id": sale.order_id,
                }
            )

        db.commit()
        return JSONResponse({"assigned": assigned, "count": len(assigned)})
    finally:
        db.close()


@app.post("/api/procurements/yahoo-local-import")
async def proc_yahoo_local_import(request: Request):
    """ローカルMacからの直接取込（VPS IP が EEA 判定される場合の回避策）"""
    import_key = request.headers.get("X-Import-Key", "")
    expected = os.getenv("YAHOO_IMPORT_KEY", "")
    if not expected or import_key != expected:
        raise HTTPException(status_code=403, detail="unauthorized")

    results = await request.json()
    if not isinstance(results, list):
        raise HTTPException(status_code=400, detail="expected list of items")

    db = get_db()
    try:
        created = 0
        skipped = 0
        for row in sorted(results, key=lambda r: r.get("date", "") or "9999"):
            title = (row.get("title") or "").strip()
            if not title:
                skipped += 1
                continue
            url = row.get("url", "")
            # URL（落札ID）で重複チェック、なければタイトル+価格で判定
            if url:
                existing = (
                    db.query(Procurement)
                    .filter(Procurement.platform == "ヤフオク", Procurement.url == url)
                    .first()
                )
            else:
                existing = (
                    db.query(Procurement)
                    .filter(
                        Procurement.platform == "ヤフオク",
                        Procurement.title == title,
                        Procurement.purchase_price_jpy == int(row.get("price", 0) or 0),
                    )
                    .first()
                )
            if existing:
                skipped += 1
                continue

            price = int(row.get("price", 0) or 0)
            tax = int(row.get("tax", 0) or 0)
            shipping = int(row.get("shipping", 0) or 0)
            is_store = bool(row.get("is_store", False))
            purchase_price = (price - tax) if (is_store and tax > 0) else price

            seller = row.get("seller", "") or ""
            seller_url = (
                f"https://auctions.yahoo.co.jp/seller/{seller}" if seller else ""
            )

            kwargs: dict = {
                "title": title,
                "platform": "ヤフオク",
                "url": url,
                "purchase_price_jpy": purchase_price,
                "consumption_tax_jpy": tax,
                "shipping_cost_jpy": shipping,
                "seller_id": seller,
                "seller_url": seller_url,
                "image_url": row.get("image_url", ""),
                "screenshot_path": row.get("screenshot_path", ""),
                "status": "purchased",
            }
            if row.get("date"):
                try:
                    kwargs["purchase_date"] = datetime.strptime(row["date"], "%Y-%m-%d")
                except ValueError:
                    pass
            crud.add_procurement(db, **kwargs)
            created += 1

        return JSONResponse(
            {"imported": created, "skipped": skipped, "total": len(results)}
        )
    finally:
        db.close()


@app.post("/api/procurements/mercari-local-import")
async def proc_mercari_local_import(request: Request):
    """ローカルMacからのメルカリ購入履歴直接取込"""
    import base64 as _b64

    from config import SCREENSHOT_DIR

    import_key = request.headers.get("X-Import-Key", "")
    expected = os.getenv("YAHOO_IMPORT_KEY", "")
    if not expected or import_key != expected:
        raise HTTPException(status_code=403, detail="unauthorized")

    results = await request.json()
    if not isinstance(results, list):
        raise HTTPException(status_code=400, detail="expected list of items")

    db = get_db()
    try:
        created = 0
        skipped = 0
        for row in sorted(results, key=lambda r: r.get("date", "") or "9999"):
            title = (row.get("title") or "").strip()
            if not title:
                skipped += 1
                continue
            price = int(row.get("price", 0) or 0)
            url = row.get("item_url", "") or row.get("transaction_url", "")
            existing = (
                db.query(Procurement)
                .filter(
                    Procurement.platform == "メルカリ",
                    Procurement.title == title,
                    Procurement.purchase_price_jpy == price,
                )
                .first()
            )
            if existing:
                # 既存レコードでSSが未設定なら補完
                if not existing.screenshot_path and row.get("screenshot_b64"):
                    _save_proc_screenshot_b64(
                        existing, row["screenshot_b64"], SCREENSHOT_DIR, db, _b64
                    )
                skipped += 1
                continue
            kwargs: dict = {
                "title": title,
                "platform": "メルカリ",
                "url": url,
                "purchase_price_jpy": price,
                "shipping_cost_jpy": int(row.get("shipping", 0) or 0),
                "image_url": row.get("image_url", ""),
                "status": "purchased",
            }
            if row.get("date"):
                try:
                    kwargs["purchase_date"] = datetime.strptime(row["date"], "%Y-%m-%d")
                except ValueError:
                    pass
            proc = crud.add_procurement(db, **kwargs)
            if row.get("screenshot_b64"):
                _save_proc_screenshot_b64(
                    proc, row["screenshot_b64"], SCREENSHOT_DIR, db, _b64
                )
            created += 1
        return JSONResponse(
            {"imported": created, "skipped": skipped, "total": len(results)}
        )
    finally:
        db.close()


def _local_import_generic(results: list, platform: str, db) -> tuple[int, int]:
    """共通ローカル取込ロジック。(created, skipped) を返す"""
    created = 0
    skipped = 0
    for row in sorted(results, key=lambda r: r.get("date", "") or "9999"):
        title = (row.get("title") or "").strip()
        if not title:
            skipped += 1
            continue
        price = int(row.get("price", 0) or 0)
        url = row.get("item_url", "") or row.get("url", "")
        existing = (
            db.query(Procurement)
            .filter(
                Procurement.platform == platform,
                Procurement.title == title,
                Procurement.purchase_price_jpy == price,
            )
            .first()
        )
        if existing:
            skipped += 1
            continue
        kwargs: dict = {
            "title": title,
            "platform": platform,
            "url": url,
            "purchase_price_jpy": price,
            "shipping_cost_jpy": int(row.get("shipping", 0) or 0),
            "image_url": row.get("image_url", ""),
            "seller_id": row.get("seller_id", "") or row.get("seller", ""),
            "seller_url": row.get("seller_url", ""),
            "status": "purchased",
        }
        if row.get("date"):
            try:
                kwargs["purchase_date"] = datetime.strptime(row["date"], "%Y-%m-%d")
            except ValueError:
                pass
        crud.add_procurement(db, **kwargs)
        created += 1
    return created, skipped


def _auth_local_import(request: Request) -> None:
    """X-Import-Key 認証。失敗時は HTTPException(403) を raise"""
    import_key = request.headers.get("X-Import-Key", "")
    expected = os.getenv("YAHOO_IMPORT_KEY", "")
    if not expected or import_key != expected:
        raise HTTPException(status_code=403, detail="unauthorized")


def _save_proc_screenshot_b64(proc, b64_str: str, ss_dir, db, b64_mod) -> None:
    """base64エンコード済みSSをVPSに保存してprocのscreenshot_pathを更新"""
    try:
        # ファイル名日付は取引日優先（古物台帳要件）。なければ今日
        date_src = proc.purchase_date or datetime.now(JST)
        if hasattr(date_src, "tzinfo") and date_src.tzinfo is None:
            date_src = date_src.replace(tzinfo=JST)
        date_str = date_src.strftime("%Y%m%d")
        year = date_src.strftime("%Y")
        platform = (proc.platform or "other").replace("/", "_").replace(" ", "_")
        dest = ss_dir / year / platform
        dest.mkdir(parents=True, exist_ok=True)
        safe = "".join(
            c for c in (proc.title or "item")[:30] if c.isalnum() or c in "-_ "
        ).strip()
        filepath = dest / f"proc{proc.id}_{date_str}_{safe}.png"
        filepath.write_bytes(b64_mod.b64decode(b64_str))
        proc.screenshot_path = str(filepath)
        db.commit()
    except Exception as e:
        logger.warning(f"SS保存失敗 proc{proc.id}: {e}")


@app.post("/api/procurements/yahoo-flea-local-import")
async def proc_yahoo_flea_local_import(request: Request):
    """ローカルMacからのYahooフリマ購入履歴直接取込"""
    _auth_local_import(request)
    results = await request.json()
    if not isinstance(results, list):
        raise HTTPException(400, "expected list of items")
    db = get_db()
    try:
        created, skipped = _local_import_generic(results, "Yahooフリマ", db)
        return JSONResponse(
            {"imported": created, "skipped": skipped, "total": len(results)}
        )
    finally:
        db.close()


@app.post("/api/procurements/rakuma-local-import")
async def proc_rakuma_local_import(request: Request):
    """ローカルMacからのラクマ購入履歴直接取込"""
    _auth_local_import(request)
    results = await request.json()
    if not isinstance(results, list):
        raise HTTPException(400, "expected list of items")
    db = get_db()
    try:
        created, skipped = _local_import_generic(results, "ラクマ", db)
        return JSONResponse(
            {"imported": created, "skipped": skipped, "total": len(results)}
        )
    finally:
        db.close()


@app.post("/api/procurements/hardoff-local-import")
async def proc_hardoff_local_import(request: Request):
    """ローカルMacからのハードオフ購入履歴直接取込"""
    _auth_local_import(request)
    results = await request.json()
    if not isinstance(results, list):
        raise HTTPException(400, "expected list of items")
    db = get_db()
    try:
        created, skipped = _local_import_generic(results, "ネットモール(OFFモール)", db)
        return JSONResponse(
            {"imported": created, "skipped": skipped, "total": len(results)}
        )
    finally:
        db.close()


@app.post("/api/procurements/surugaya-local-import")
async def proc_surugaya_local_import(request: Request):
    """ローカルMacからの駿河屋購入履歴直接取込"""
    _auth_local_import(request)
    results = await request.json()
    if not isinstance(results, list):
        raise HTTPException(400, "expected list of items")
    db = get_db()
    try:
        created, skipped = _local_import_generic(results, "駿河屋", db)
        return JSONResponse(
            {"imported": created, "skipped": skipped, "total": len(results)}
        )
    finally:
        db.close()


@app.post("/api/procurements/auto-category")
async def proc_auto_category():
    """古物区分が未設定の仕入れレコードにタイトルから自動判定して一括付与"""
    db = get_db()
    try:
        targets = (
            db.query(Procurement)
            .filter((Procurement.category == None) | (Procurement.category == ""))
            .all()
        )
        updated = 0
        skipped = 0
        for proc in targets:
            cat = crud.guess_kobutsu_category(proc.title or "")
            if cat:
                proc.category = cat
                updated += 1
            else:
                skipped += 1
        db.commit()
        return JSONResponse(
            {"updated": updated, "skipped": skipped, "total": len(targets)}
        )
    finally:
        db.close()


@app.post("/api/procurements/sync-sku-from-ebay")
async def sync_sku_from_ebay():
    """ebay_item_id があり SKU 未設定の仕入れレコードに eBay CustomLabel を同期"""
    from ebay_core.client import get_item_trading

    db = get_db()
    try:
        targets = (
            db.query(Procurement)
            .filter(
                Procurement.ebay_item_id != None,
                Procurement.ebay_item_id != "",
                (Procurement.sku == None) | (Procurement.sku == ""),
            )
            .all()
        )
        updated = 0
        errors = []
        for proc in targets:
            info = get_item_trading(proc.ebay_item_id)
            if info.get("ok") and info.get("sku"):
                proc.sku = info["sku"]
                updated += 1
            elif not info.get("ok"):
                errors.append(
                    {"item_id": proc.ebay_item_id, "error": info.get("error")}
                )
        db.commit()
        return JSONResponse(
            {"updated": updated, "skipped": len(targets) - updated, "errors": errors}
        )
    finally:
        db.close()


@app.post("/api/admin/stale-reminder")
async def stale_procurement_reminder(days: int = 7):
    """purchased 状態のまま N 日以上経過した仕入れを Telegram に通知"""
    from database.models import JST

    db = get_db()
    try:
        cutoff = datetime.now(JST) - timedelta(days=days)
        stale = (
            db.query(Procurement)
            .filter(
                Procurement.status == "purchased",
                Procurement.purchase_date.isnot(None),
                Procurement.purchase_date <= cutoff,
            )
            .order_by(Procurement.purchase_date)
            .all()
        )
        if not stale:
            return {"notified": 0, "message": "滞留なし"}

        lines = [f"📦 仕入れ滞留アラート（{days}日以上 purchased）\n"]
        for p in stale[:10]:
            elapsed = (datetime.now(JST).replace(tzinfo=None) - p.purchase_date).days
            lines.append(
                f"• {p.stock_number or f'ID:{p.id}'} — {p.title[:30]}…\n"
                f"  仕入日: {p.purchase_date.strftime('%Y-%m-%d')} ({elapsed}日経過)"
            )
        if len(stale) > 10:
            lines.append(f"… 他 {len(stale) - 10} 件")

        import requests as _req
        from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            _req.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": "\n".join(lines)},
                timeout=10,
            )
        return {"notified": len(stale)}
    finally:
        db.close()


@app.post("/api/admin/resync-costs")
async def resync_procurement_costs():
    """Procurement と紐づく SalesRecord のコストを一括再同期
    source_cost_jpy=0 かつ ebay_order_id が一致する仕入れが存在するレコードを修正"""
    from database.models import SalesRecord as _SR

    db = get_db()
    try:
        # ebay_order_id を持つ仕入れ一覧
        procs = db.query(Procurement).filter(Procurement.ebay_order_id != "").all()
        proc_by_order = {p.ebay_order_id: p for p in procs}

        updated = 0
        skipped = 0
        for order_id, proc in proc_by_order.items():
            sale = db.query(_SR).filter(_SR.order_id == order_id).first()
            if not sale:
                skipped += 1
                continue
            # コストが既に正しければスキップ
            if (
                sale.source_cost_jpy == proc.purchase_price_jpy
                and sale.shipping_cost_jpy == proc.shipping_cost_jpy
                and sale.consumption_tax_jpy == proc.consumption_tax_jpy
            ):
                skipped += 1
                continue
            crud.update_sales_record(
                db,
                sale.id,
                source_cost_jpy=proc.purchase_price_jpy,
                shipping_cost_jpy=proc.shipping_cost_jpy,
                consumption_tax_jpy=proc.consumption_tax_jpy,
            )
            updated += 1

        return {"updated": updated, "skipped": skipped}
    finally:
        db.close()


@app.post("/api/admin/price-drop-reminder")
async def price_drop_reminder(days: int = 30):
    """listed 状態のまま N 日以上経過した仕入れを値下げ提案としてTelegramに通知"""
    from database.models import JST

    db = get_db()
    try:
        cutoff = datetime.now(JST) - timedelta(days=days)
        stale = (
            db.query(Procurement)
            .filter(
                Procurement.status == "listed",
                Procurement.listed_at.isnot(None),
                Procurement.listed_at <= cutoff,
            )
            .order_by(Procurement.listed_at)
            .all()
        )
        if not stale:
            return {"notified": 0, "message": "値下げ候補なし"}

        lines = [f"📉 値下げ検討リスト（{days}日以上 listed）\n"]
        for p in stale[:10]:
            elapsed = (datetime.now(JST).replace(tzinfo=None) - p.listed_at).days
            price_info = (
                f"¥{p.purchase_price_jpy:,}" if p.purchase_price_jpy else "不明"
            )
            ebay_info = f" eBay:{p.ebay_item_id}" if p.ebay_item_id else ""
            lines.append(
                f"• {p.stock_number or f'ID:{p.id}'} — {p.title[:28]}…\n"
                f"  仕入:{price_info} / 出品{elapsed}日経過{ebay_info}"
            )
        if len(stale) > 10:
            lines.append(f"… 他 {len(stale) - 10} 件")

        import requests as _req
        from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            _req.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": "\n".join(lines)},
                timeout=10,
            )
        return {"notified": len(stale)}
    finally:
        db.close()


@app.post("/api/admin/batch-defaults")
async def batch_defaults(request: Request):
    """既存レコードのデフォルト値一括設定 + 管理番号採番"""
    expected = os.getenv("YAHOO_IMPORT_KEY", "")
    key = request.headers.get("x-import-key", "")
    if not expected or key != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
    db = get_db()
    try:
        # location: NULL/空 → 自宅
        updated_loc = (
            db.query(Procurement)
            .filter((Procurement.location == None) | (Procurement.location == ""))
            .update({"location": "自宅"}, synchronize_session=False)
        )
        db.flush()
        # stock_number: 未設定のものに P-XXXX 採番
        procs_no_sn = (
            db.query(Procurement)
            .filter(
                (Procurement.stock_number == None) | (Procurement.stock_number == "")
            )
            .order_by(Procurement.id)
            .all()
        )
        for proc in procs_no_sn:
            proc.stock_number = crud._next_proc_stock_number(db)
            db.flush()
        db.commit()
        return JSONResponse(
            {"location_updated": updated_loc, "stock_number_assigned": len(procs_no_sn)}
        )
    finally:
        db.close()


@app.post("/api/procurements/scrape/yahoo-flea")
async def proc_start_yahoo_flea_scrape():
    import uuid

    job_id = str(uuid.uuid4())[:8]
    _scrape_jobs[job_id] = {
        "status": "running",
        "message": "初期化中...",
        "current": 0,
        "total": 0,
        "results": [],
        "error": None,
    }

    async def run_scrape():
        from scrapers.yahoo_flea_purchases import scrape_yahoo_flea_purchases

        job = _scrape_jobs[job_id]
        try:

            def on_progress(msg, cur, total):
                job["message"] = msg
                job["current"] = cur
                job["total"] = total

            results = await scrape_yahoo_flea_purchases(
                on_progress=on_progress, headless=SCRAPER_HEADLESS
            )
            job["results"] = results
            job["status"] = "done"
            job["message"] = f"完了: {len(results)}件取得"
        except RuntimeError as e:
            if str(e) == "LOGIN_REQUIRED":
                job["status"] = "login_required"
                job["message"] = "Yahooフリマログインが必要です。"
                _notify_login_required("yahoo_flea", "Yahooフリマ")
            else:
                job["status"] = "error"
                job["error"] = str(e)
                job["message"] = f"エラー: {e}"
        except Exception as e:
            job["status"] = "error"
            job["error"] = str(e)
            job["message"] = f"エラー: {e}"

    asyncio.create_task(run_scrape())
    return JSONResponse({"job_id": job_id, "status": "started"})


@app.post("/api/procurements/scrape/yahoo-flea/import/{job_id}")
async def proc_import_yahoo_flea_results(job_id: str):
    job = _scrape_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "done":
        raise HTTPException(400, f"Job not ready: {job['status']}")
    results = sorted(job.get("results", []), key=lambda r: r.get("date", "") or "9999")
    db = get_db()
    try:
        created = 0
        skipped = 0
        for row in results:
            title = (row.get("title") or "").strip()
            if not title:
                skipped += 1
                continue
            price = int(row.get("price", 0) or 0)
            existing = (
                db.query(Procurement)
                .filter(
                    Procurement.title == title,
                    Procurement.purchase_price_jpy == price,
                    Procurement.platform == "Yahooフリマ",
                )
                .first()
            )
            if existing:
                skipped += 1
                continue
            kwargs = {
                "title": title,
                "purchase_price_jpy": price,
                "platform": "Yahooフリマ",
                "url": row.get("item_url", "") or row.get("url", ""),
                "image_url": row.get("image_url", ""),
                "screenshot_path": row.get("screenshot_path", ""),
                "status": "purchased",
            }
            if row.get("date"):
                try:
                    kwargs["purchase_date"] = datetime.strptime(row["date"], "%Y-%m-%d")
                except ValueError:
                    pass
            crud.add_procurement(db, **kwargs)
            created += 1
        _scrape_jobs.pop(job_id, None)
        return JSONResponse(
            {
                "status": "imported",
                "created": created,
                "skipped": skipped,
                "total": len(results),
            }
        )
    finally:
        db.close()


@app.post("/api/procurements/scrape/rakuma")
async def proc_start_rakuma_scrape():
    import uuid

    job_id = str(uuid.uuid4())[:8]
    _scrape_jobs[job_id] = {
        "status": "running",
        "message": "初期化中...",
        "current": 0,
        "total": 0,
        "results": [],
        "error": None,
    }

    async def run_scrape():
        from scrapers.rakuma import scrape_rakuma_purchases

        job = _scrape_jobs[job_id]
        try:

            def on_progress(msg, cur, total):
                job["message"] = msg
                job["current"] = cur
                job["total"] = total

            results = await scrape_rakuma_purchases(
                on_progress=on_progress, headless=SCRAPER_HEADLESS
            )
            job["results"] = results
            job["status"] = "done"
            job["message"] = f"完了: {len(results)}件取得"
        except RuntimeError as e:
            if str(e) == "LOGIN_REQUIRED":
                job["status"] = "login_required"
                job["message"] = "ラクマログインが必要です。"
                _notify_login_required("rakuma", "ラクマ")
            else:
                job["status"] = "error"
                job["error"] = str(e)
                job["message"] = f"エラー: {e}"
        except Exception as e:
            job["status"] = "error"
            job["error"] = str(e)
            job["message"] = f"エラー: {e}"

    asyncio.create_task(run_scrape())
    return JSONResponse({"job_id": job_id, "status": "started"})


@app.post("/api/procurements/scrape/rakuma/import/{job_id}")
async def proc_import_rakuma_results(job_id: str):
    job = _scrape_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "done":
        raise HTTPException(400, f"Job not ready: {job['status']}")
    results = sorted(job.get("results", []), key=lambda r: r.get("date", "") or "9999")
    db = get_db()
    try:
        created = 0
        skipped = 0
        for row in results:
            title = (row.get("title") or "").strip()
            if not title:
                skipped += 1
                continue
            price = int(row.get("price", 0) or 0)
            existing = (
                db.query(Procurement)
                .filter(
                    Procurement.title == title,
                    Procurement.purchase_price_jpy == price,
                    Procurement.platform == "ラクマ",
                )
                .first()
            )
            if existing:
                skipped += 1
                continue
            kwargs = {
                "title": title,
                "purchase_price_jpy": price,
                "platform": "ラクマ",
                "url": row.get("item_url", "") or row.get("url", ""),
                "image_url": row.get("image_url", ""),
                "screenshot_path": row.get("screenshot_path", ""),
                "status": "purchased",
            }
            if row.get("date"):
                try:
                    kwargs["purchase_date"] = datetime.strptime(row["date"], "%Y-%m-%d")
                except ValueError:
                    pass
            crud.add_procurement(db, **kwargs)
            created += 1
        _scrape_jobs.pop(job_id, None)
        return JSONResponse(
            {
                "status": "imported",
                "created": created,
                "skipped": skipped,
                "total": len(results),
            }
        )
    finally:
        db.close()


@app.post("/api/procurements/scrape/hardoff")
async def proc_start_hardoff_scrape():
    import uuid

    job_id = str(uuid.uuid4())[:8]
    _scrape_jobs[job_id] = {
        "status": "running",
        "message": "初期化中...",
        "current": 0,
        "total": 0,
        "results": [],
        "error": None,
    }

    async def run_scrape():
        from scrapers.hardoff import scrape_hardoff_purchases

        job = _scrape_jobs[job_id]
        try:

            def on_progress(msg, cur, total):
                job["message"] = msg
                job["current"] = cur
                job["total"] = total

            results = await scrape_hardoff_purchases(
                on_progress=on_progress, headless=SCRAPER_HEADLESS
            )
            job["results"] = results
            job["status"] = "done"
            job["message"] = f"完了: {len(results)}件取得"
        except Exception as e:
            job["status"] = "error"
            job["error"] = str(e)
            job["message"] = f"エラー: {e}"

    asyncio.create_task(run_scrape())
    return JSONResponse({"job_id": job_id, "status": "started"})


@app.post("/api/procurements/scrape/hardoff/import/{job_id}")
async def proc_import_hardoff_results(job_id: str):
    job = _scrape_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "done":
        raise HTTPException(400, f"Job not ready: {job['status']}")
    results = sorted(job.get("results", []), key=lambda r: r.get("date", "") or "9999")
    db = get_db()
    try:
        created = 0
        skipped = 0
        for row in results:
            title = (row.get("title") or "").strip()
            if not title:
                skipped += 1
                continue
            price = int(row.get("price", 0) or 0)
            existing = (
                db.query(Procurement)
                .filter(
                    Procurement.title == title,
                    Procurement.purchase_price_jpy == price,
                    Procurement.platform == "ネットモール(OFFモール)",
                )
                .first()
            )
            if existing:
                skipped += 1
                continue
            kwargs = {
                "title": title,
                "purchase_price_jpy": price,
                "platform": "ネットモール(OFFモール)",
                "url": row.get("item_url", "") or row.get("url", ""),
                "image_url": row.get("image_url", ""),
                "screenshot_path": row.get("screenshot_path", ""),
                "status": "purchased",
            }
            if row.get("date"):
                try:
                    kwargs["purchase_date"] = datetime.strptime(row["date"], "%Y-%m-%d")
                except ValueError:
                    pass
            crud.add_procurement(db, **kwargs)
            created += 1
        _scrape_jobs.pop(job_id, None)
        return JSONResponse(
            {
                "status": "imported",
                "created": created,
                "skipped": skipped,
                "total": len(results),
            }
        )
    finally:
        db.close()


@app.post("/api/procurements/scrape/surugaya")
async def proc_start_surugaya_scrape():
    import uuid

    job_id = str(uuid.uuid4())[:8]
    _scrape_jobs[job_id] = {
        "status": "running",
        "message": "初期化中...",
        "current": 0,
        "total": 0,
        "results": [],
        "error": None,
    }

    async def run_scrape():
        from scrapers.surugaya import scrape_surugaya_purchases

        job = _scrape_jobs[job_id]
        try:

            def on_progress(msg, cur, total):
                job["message"] = msg
                job["current"] = cur
                job["total"] = total

            results = await scrape_surugaya_purchases(
                on_progress=on_progress, headless=SCRAPER_HEADLESS
            )
            job["results"] = results
            job["status"] = "done"
            job["message"] = f"完了: {len(results)}件取得"
        except Exception as e:
            job["status"] = "error"
            job["error"] = str(e)
            job["message"] = f"エラー: {e}"

    asyncio.create_task(run_scrape())
    return JSONResponse({"job_id": job_id, "status": "started"})


@app.post("/api/procurements/scrape/surugaya/import/{job_id}")
async def proc_import_surugaya_results(job_id: str):
    job = _scrape_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "done":
        raise HTTPException(400, f"Job not ready: {job['status']}")
    results = sorted(job.get("results", []), key=lambda r: r.get("date", "") or "9999")
    db = get_db()
    try:
        created = 0
        skipped = 0
        for row in results:
            title = (row.get("title") or "").strip()
            if not title:
                skipped += 1
                continue
            price = int(row.get("price", 0) or 0)
            existing = (
                db.query(Procurement)
                .filter(
                    Procurement.title == title,
                    Procurement.purchase_price_jpy == price,
                    Procurement.platform == "駿河屋",
                )
                .first()
            )
            if existing:
                skipped += 1
                continue
            kwargs = {
                "title": title,
                "purchase_price_jpy": price,
                "platform": "駿河屋",
                "url": row.get("item_url", "") or row.get("url", ""),
                "image_url": row.get("image_url", ""),
                "screenshot_path": row.get("screenshot_path", ""),
                "status": "purchased",
            }
            if row.get("date"):
                try:
                    kwargs["purchase_date"] = datetime.strptime(row["date"], "%Y-%m-%d")
                except ValueError:
                    pass
            crud.add_procurement(db, **kwargs)
            created += 1
        _scrape_jobs.pop(job_id, None)
        return JSONResponse(
            {
                "status": "imported",
                "created": created,
                "skipped": skipped,
                "total": len(results),
            }
        )
    finally:
        db.close()


@app.post("/api/procurements/{proc_id}/screenshot")
async def upload_procurement_screenshot(proc_id: int, request: Request):
    """仕入れ記録スクリーンショットをアップロード"""
    from config import SCREENSHOT_DIR

    db = get_db()
    try:
        proc = db.query(Procurement).filter(Procurement.id == proc_id).first()
        if not proc:
            raise HTTPException(404, "Procurement not found")

        form = await request.form()
        file = form.get("file")
        if not file:
            raise HTTPException(400, "No file uploaded")

        now = datetime.now(JST)
        year = str(now.year)
        platform = proc.platform or "other"
        platform_dir = (
            SCREENSHOT_DIR / year / platform.replace("/", "_").replace(" ", "_")
        )
        platform_dir.mkdir(parents=True, exist_ok=True)

        ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "png"
        safe_title = "".join(
            c for c in (proc.title or "item")[:30] if c.isalnum() or c in "-_ "
        ).strip()
        filename = f"proc{proc.id}_{now.strftime('%Y%m%d')}_{safe_title}.{ext}"
        filepath = platform_dir / filename

        with open(filepath, "wb") as f:
            content = await file.read()
            f.write(content)

        proc.screenshot_path = str(filepath)
        db.commit()

        return JSONResponse(
            {
                "status": "uploaded",
                "path": str(filepath),
                "platform_dir": str(platform_dir),
            }
        )
    finally:
        db.close()


@app.post("/api/procurements/{proc_id}/screenshot-patch")
async def patch_procurement_screenshot(proc_id: int, request: Request):
    """base64エンコード済みSSを受け取りSSなしレコードに補完する"""
    _auth_local_import(request)
    from config import SCREENSHOT_DIR
    import base64 as _b64

    db = get_db()
    try:
        proc = db.query(Procurement).filter(Procurement.id == proc_id).first()
        if not proc:
            raise HTTPException(404, "Procurement not found")
        if proc.screenshot_path:
            return JSONResponse(
                {"status": "skipped", "reason": "already has screenshot"}
            )

        body = await request.json()
        b64_str = body.get("screenshot_b64", "")
        if not b64_str:
            raise HTTPException(400, "screenshot_b64 is required")

        _save_proc_screenshot_b64(proc, b64_str, SCREENSHOT_DIR, db, _b64)
        return JSONResponse({"status": "patched", "path": proc.screenshot_path})
    finally:
        db.close()


@app.get("/api/procurements/{proc_id}/screenshot")
async def get_procurement_screenshot(proc_id: int):
    from fastapi.responses import FileResponse, Response

    db = get_db()
    try:
        proc = db.query(Procurement).filter(Procurement.id == proc_id).first()
        if not proc or not proc.screenshot_path:
            raise HTTPException(404, "Screenshot not found")
        ss = proc.screenshot_path
        if ss.startswith("/static/"):
            filepath = Path(__file__).parent / ss.lstrip("/")
        elif ss.startswith("static/"):
            filepath = Path(__file__).parent / ss
        else:
            filepath = Path(ss)
        if not filepath.exists():
            # Fallback: filename may be truncated on disk (e.g. Japanese chars cut off)
            # Search parent directory for any file starting with proc{proc_id}_
            parent = filepath.parent
            candidates = (
                list(parent.glob(f"proc{proc_id}_*")) if parent.exists() else []
            )
            if candidates:
                filepath = candidates[0]
            else:
                raise HTTPException(404, "Screenshot file not found")
        if filepath.stat().st_size > 5_000_000:
            try:
                from PIL import Image
                import io as _io

                img = Image.open(filepath)
                max_width = 800
                if img.width > max_width:
                    ratio = max_width / img.width
                    img = img.resize(
                        (max_width, int(img.height * ratio)), Image.LANCZOS
                    )
                if img.height > 6000:
                    img = img.crop((0, 0, img.width, 6000))
                buf = _io.BytesIO()
                img.save(buf, format="JPEG", quality=70)
                return Response(content=buf.getvalue(), media_type="image/jpeg")
            except Exception:
                pass
        return FileResponse(str(filepath))
    finally:
        db.close()


# ── Instagram API ─────────────────────────────────────────


@app.post("/api/instagram/generate")
async def instagram_generate_endpoint(request: Request):
    """Instagram投稿キャプション生成"""
    body = await request.json()
    result = await handle_tool_call("generate_instagram_post", body)
    return JSONResponse(json.loads(result))


@app.post("/api/instagram/publish")
async def instagram_publish_endpoint(request: Request):
    """Instagram投稿を公開"""
    body = await request.json()
    result = await handle_tool_call("publish_instagram_post", body)
    return JSONResponse(json.loads(result))


@app.get("/api/instagram/analytics")
async def instagram_analytics_endpoint(days: int = 30):
    """Instagram分析データ取得"""
    result = await handle_tool_call("get_instagram_analytics", {"days": days})
    return JSONResponse(json.loads(result))


@app.get("/api/instagram/posts")
async def instagram_posts_endpoint(status: str = ""):
    """Instagram投稿一覧"""
    from database.models import InstagramPost
    from sqlalchemy import desc

    db = get_db()
    try:
        q = db.query(InstagramPost)
        if status:
            q = q.filter(InstagramPost.status == status)
        posts = q.order_by(desc(InstagramPost.created_at)).limit(50).all()
        return [
            {
                "id": p.id,
                "sku": p.sku,
                "content_type": p.content_type,
                "tone": p.tone,
                "status": p.status,
                "caption_preview": p.caption[:120] + "..."
                if len(p.caption) > 120
                else p.caption,
                "hashtag_count": len(json.loads(p.hashtags_json))
                if p.hashtags_json
                else 0,
                "image_count": len(json.loads(p.image_urls_json))
                if p.image_urls_json
                else 0,
                "impressions": p.impressions,
                "likes": p.likes,
                "saves": p.saves,
                "created_at": p.created_at.isoformat(),
                "published_at": p.published_at.isoformat() if p.published_at else None,
                "scheduled_at": p.scheduled_at.isoformat() if p.scheduled_at else None,
            }
            for p in posts
        ]
    finally:
        db.close()


@app.get("/api/instagram/posts/{post_id}")
async def instagram_post_detail(post_id: int):
    """Instagram投稿詳細"""
    from database.models import InstagramPost

    db = get_db()
    try:
        post = db.query(InstagramPost).filter(InstagramPost.id == post_id).first()
        if not post:
            raise HTTPException(status_code=404, detail=f"Post {post_id} not found")
        return {
            "id": post.id,
            "sku": post.sku,
            "caption": post.caption,
            "hashtags": json.loads(post.hashtags_json) if post.hashtags_json else [],
            "content_type": post.content_type,
            "tone": post.tone,
            "cta": post.cta,
            "image_urls": json.loads(post.image_urls_json)
            if post.image_urls_json
            else [],
            "slide_suggestions": json.loads(post.slide_suggestions_json)
            if post.slide_suggestions_json
            else [],
            "status": post.status,
            "ig_post_id": post.ig_post_id,
            "impressions": post.impressions,
            "reach": post.reach,
            "likes": post.likes,
            "comments": post.comments,
            "saves": post.saves,
            "link_clicks": post.link_clicks,
            "created_at": post.created_at.isoformat(),
            "published_at": post.published_at.isoformat()
            if post.published_at
            else None,
            "scheduled_at": post.scheduled_at.isoformat()
            if post.scheduled_at
            else None,
        }
    finally:
        db.close()


@app.post("/api/instagram/dm-reply")
async def instagram_dm_reply_endpoint(request: Request):
    """DM返信ドラフト生成"""
    body = await request.json()
    result = await handle_tool_call("generate_dm_reply", body)
    return JSONResponse(json.loads(result))


# ── 利益管理 ─────────────────────────────────────────────


@app.get("/profit", response_class=HTMLResponse)
async def profit_redirect():
    return RedirectResponse(url="/sales", status_code=301)


@app.get("/api/profit/summary")
async def profit_summary_api(months: int = 6):
    db = get_db()
    try:
        return JSONResponse(crud.get_profit_summary(db, months=months))
    finally:
        db.close()


@app.get("/api/profit/breakdown")
async def profit_breakdown_api(month: str = ""):
    if not month:
        from datetime import datetime

        month = datetime.utcnow().strftime("%Y-%m")
    db = get_db()
    try:
        return JSONResponse(crud.get_profit_breakdown(db, year_month=month))
    finally:
        db.close()


@app.get("/api/sales/records")
async def sales_records_api(month: str = "", from_date: str = "", to_date: str = ""):
    db = get_db()
    try:
        from database.models import Listing, Procurement
        from dateutil.relativedelta import relativedelta

        # 期間コード（1M, 3M, 6M, 12M）→ 日付範囲に変換
        period_months = {"1M": 1, "3M": 3, "6M": 6, "12M": 12}
        ym = ""
        if month in period_months:
            from_date = (
                datetime.utcnow() - relativedelta(months=period_months[month])
            ).strftime("%Y-%m-%d")
            to_date = ""  # 現在まで
        elif month:
            ym = month  # YYYY-MM形式

        records = crud.get_all_sales(db, year_month=ym)

        # 日付範囲フィルタ
        if from_date:
            try:
                fd = datetime.strptime(from_date, "%Y-%m-%d")
                records = [r for r in records if r.sold_at and r.sold_at >= fd]
            except ValueError:
                pass
        if to_date:
            try:
                td = datetime.strptime(to_date, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59
                )
                records = [r for r in records if r.sold_at and r.sold_at <= td]
            except ValueError:
                pass

        # SKU→画像URLマップ（一括取得）
        skus = list({r.sku for r in records if r.sku})
        image_map = {}
        if skus:
            listings = (
                db.query(Listing.sku, Listing.image_urls_json)
                .filter(Listing.sku.in_(skus))
                .all()
            )
            for l in listings:
                try:
                    urls = json.loads(l.image_urls_json) if l.image_urls_json else []
                    if urls:
                        image_map[l.sku] = urls[0]
                except (json.JSONDecodeError, IndexError):
                    pass

        # SKU→仕入情報マップ（一括取得）
        proc_map = {}
        if skus:
            procs = (
                db.query(Procurement)
                .filter(Procurement.sku.in_(skus))
                .order_by(Procurement.created_at.desc())
                .all()
            )
            for p in procs:
                if p.sku not in proc_map:
                    proc_map[p.sku] = p

        # order_id → 仕入れマップ（主キー: ebay_order_id が一致する仕入れ）
        proc_by_order_id: dict = {}
        linked_procs = (
            db.query(Procurement).filter(Procurement.ebay_order_id != "").all()
        )
        for p in linked_procs:
            if p.ebay_order_id not in proc_by_order_id:
                proc_by_order_id[p.ebay_order_id] = p

        result = []
        for r in records:
            rate = r.exchange_rate or 1.0
            sale_jpy = round(r.sale_price_usd * rate)
            fees_jpy = round((r.ebay_fees_usd + r.payoneer_fee_usd) * rate)

            p = proc_by_order_id.get(r.order_id) or proc_map.get(r.sku)
            proc_info = None
            if p:
                proc_info = {
                    "id": p.id,
                    "purchase_date": p.purchase_date.strftime("%Y-%m-%d")
                    if p.purchase_date
                    else "",
                    "purchase_price_jpy": p.purchase_price_jpy,
                    "consumption_tax_jpy": p.consumption_tax_jpy,
                    "shipping_cost_jpy": p.shipping_cost_jpy,
                    "total_cost_jpy": p.total_cost_jpy,
                    "platform": p.platform,
                    "url": p.url,
                    "status": p.status,
                }

            result.append(
                {
                    "id": r.id,
                    "order_id": r.order_id,
                    "item_id": getattr(r, "item_id", ""),
                    "sku": r.sku,
                    "title": r.title,
                    "image_url": image_map.get(r.sku, ""),
                    "buyer_name": getattr(r, "buyer_name", ""),
                    "buyer_country": getattr(r, "buyer_country", ""),
                    "sale_price_usd": r.sale_price_usd,
                    "sale_price_jpy": sale_jpy,
                    "source_cost_jpy": r.source_cost_jpy,
                    "consumption_tax_jpy": r.consumption_tax_jpy,
                    "shipping_cost_jpy": r.shipping_cost_jpy,
                    "intl_shipping_cost_jpy": r.intl_shipping_cost_jpy,
                    "shipping_method": r.shipping_method,
                    "ebay_fees_usd": r.ebay_fees_usd,
                    "payoneer_fee_usd": r.payoneer_fee_usd,
                    "fees_jpy": fees_jpy,
                    "payoneer_rate": r.payoneer_rate,
                    "received_jpy": r.received_jpy,
                    "customs_duty_jpy": getattr(r, "customs_duty_jpy", 0) or 0,
                    "other_cost_jpy": r.other_cost_jpy,
                    "cost_note": r.cost_note or "",
                    "tracking_number": r.tracking_number or "",
                    "exchange_rate": r.exchange_rate,
                    "total_cost_jpy": r.total_cost_jpy,
                    "net_profit_usd": r.net_profit_usd,
                    "net_profit_jpy": r.net_profit_jpy,
                    "profit_margin_pct": r.profit_margin_pct,
                    "sold_at": r.sold_at.strftime("%Y-%m-%d") if r.sold_at else "",
                    "progress": getattr(r, "progress", "") or "",
                    "marketplace": getattr(r, "marketplace", "") or "",
                    "listing_site": getattr(r, "listing_site", "") or "",
                    "ship_by_date": r.ship_by_date.strftime("%Y-%m-%d")
                    if getattr(r, "ship_by_date", None)
                    else "",
                    "procurement": proc_info,
                }
            )
        return JSONResponse(result)
    finally:
        db.close()


@app.put("/api/sales/{record_id}")
async def update_sales_record_api(record_id: int, request: Request):
    body = await request.json()
    db = get_db()
    try:
        record = crud.update_sales_record(db, record_id, **body)
        if not record:
            raise HTTPException(404, "Sales record not found")
        return JSONResponse(
            {
                "id": record.id,
                "net_profit_usd": record.net_profit_usd,
                "net_profit_jpy": record.net_profit_jpy,
                "profit_margin_pct": record.profit_margin_pct,
                "total_cost_jpy": record.total_cost_jpy,
            }
        )
    finally:
        db.close()


@app.get("/api/expenses")
async def get_expenses_api(month: str = ""):
    db = get_db()
    try:
        expenses = crud.get_expenses(db, year_month=month)
        return JSONResponse(
            [
                {
                    "id": e.id,
                    "year_month": e.year_month,
                    "category": e.category,
                    "description": e.description,
                    "amount_jpy": e.amount_jpy,
                    "amount_usd": e.amount_usd,
                    "is_recurring": bool(e.is_recurring),
                }
                for e in expenses
            ]
        )
    finally:
        db.close()


@app.post("/api/expenses")
async def add_expense_api(request: Request):
    body = await request.json()
    db = get_db()
    try:
        expense = crud.add_expense(db, **body)
        return JSONResponse({"id": expense.id, "status": "created"})
    finally:
        db.close()


@app.delete("/api/expenses/{expense_id}")
async def delete_expense_api(expense_id: int):
    db = get_db()
    try:
        if not crud.delete_expense(db, expense_id):
            raise HTTPException(404, "Expense not found")
        return JSONResponse({"status": "deleted"})
    finally:
        db.close()


@app.get("/api/export/tax-report")
async def export_tax_report_api(
    type: str = "sales", year: str = "", from_month: str = "", to_month: str = ""
):
    """税務エクスポート CSV"""
    import csv
    import io
    from datetime import datetime as dt
    from fastapi.responses import StreamingResponse

    db = get_db()
    try:
        output = io.StringIO()
        # BOM for Excel
        output.write("\ufeff")

        if type == "sales":
            # 売上明細（税理士メイン資料）
            writer = csv.writer(output)
            writer.writerow(
                [
                    "日付",
                    "注文ID",
                    "SKU",
                    "商品名",
                    "売上(USD)",
                    "為替レート",
                    "売上(JPY)",
                    "仕入原価(JPY)",
                    "消費税(JPY)",
                    "国内送料(JPY)",
                    "国際送料(JPY)",
                    "発送方法",
                    "eBay手数料(USD)",
                    "eBay手数料(JPY)",
                    "Payoneer手数料(USD)",
                    "Payoneer手数料(JPY)",
                    "その他経費(JPY)",
                    "経費メモ",
                    "全コスト(JPY)",
                    "純利益(JPY)",
                    "利益率(%)",
                    "Payoneerレート",
                    "実着金額(JPY)",
                    "為替差損益(JPY)",
                ]
            )
            # 期間フィルタ
            records = (
                db.query(crud.SalesRecord).order_by(crud.SalesRecord.sold_at).all()
            )
            for r in records:
                sold_ym = r.sold_at.strftime("%Y-%m") if r.sold_at else ""
                if from_month and sold_ym < from_month:
                    continue
                if to_month and sold_ym > to_month:
                    continue
                if year and not sold_ym.startswith(year):
                    continue
                rate = r.exchange_rate or 1.0
                revenue_jpy = round(r.sale_price_usd * rate)
                ebay_fees_jpy = round(r.ebay_fees_usd * rate)
                payoneer_fees_jpy = round(r.payoneer_fee_usd * rate)
                # 為替差損益 = Payoneer実着金 - TTM換算売上×(1-手数料率)
                ttm_net_jpy = round(
                    (r.sale_price_usd - r.ebay_fees_usd - r.payoneer_fee_usd) * rate
                )
                forex_diff = (r.received_jpy - ttm_net_jpy) if r.received_jpy else 0
                writer.writerow(
                    [
                        r.sold_at.strftime("%Y-%m-%d") if r.sold_at else "",
                        r.order_id,
                        r.sku,
                        r.title,
                        f"{r.sale_price_usd:.2f}",
                        f"{rate:.2f}",
                        revenue_jpy,
                        r.source_cost_jpy,
                        r.consumption_tax_jpy,
                        r.shipping_cost_jpy,
                        r.intl_shipping_cost_jpy,
                        r.shipping_method,
                        f"{r.ebay_fees_usd:.2f}",
                        ebay_fees_jpy,
                        f"{r.payoneer_fee_usd:.2f}",
                        payoneer_fees_jpy,
                        r.other_cost_jpy,
                        r.cost_note or "",
                        r.total_cost_jpy,
                        r.net_profit_jpy,
                        f"{r.profit_margin_pct:.1f}",
                        f"{r.payoneer_rate:.2f}" if r.payoneer_rate else "",
                        r.received_jpy or "",
                        forex_diff if r.received_jpy else "",
                    ]
                )
            filename = f"ebay_sales_{from_month or year or 'all'}_{to_month or ''}.csv"

        elif type == "monthly":
            # 月次集計（確定申告用）
            writer = csv.writer(output)
            writer.writerow(
                [
                    "年月",
                    "売上件数",
                    "売上合計(USD)",
                    "売上合計(JPY)",
                    "仕入原価(JPY)",
                    "消費税還付対象(JPY)",
                    "国内送料(JPY)",
                    "国際送料(JPY)",
                    "eBay手数料(USD)",
                    "Payoneer手数料(USD)",
                    "その他経費(JPY)",
                    "固定費(JPY)",
                    "経費合計(JPY)",
                    "純利益(JPY)",
                ]
            )
            summary = crud.get_profit_summary(db, months=24)
            for m in sorted(summary, key=lambda x: x["year_month"]):
                if year and not m["year_month"].startswith(year):
                    continue
                total_fees_jpy = (
                    round(
                        (m["ebay_fees_usd"] + m["payoneer_fees_usd"])
                        * (m.get("avg_rate", 150))
                    )
                    if m.get("revenue_usd")
                    else 0
                )
                expense_total = (
                    m["source_cost_jpy"]
                    + m["shipping_jpy"]
                    + m["intl_shipping_jpy"]
                    + m["other_cost_jpy"]
                    + m.get("fixed_cost_jpy", 0)
                    + total_fees_jpy
                )
                writer.writerow(
                    [
                        m["year_month"],
                        m["sales_count"],
                        f"{m['revenue_usd']:.2f}",
                        m["revenue_jpy"],
                        m["source_cost_jpy"],
                        m["consumption_tax_jpy"],
                        m["shipping_jpy"],
                        m["intl_shipping_jpy"],
                        f"{m['ebay_fees_usd']:.2f}",
                        f"{m['payoneer_fees_usd']:.2f}",
                        m["other_cost_jpy"],
                        m.get("fixed_cost_jpy", 0),
                        expense_total,
                        m["net_profit_jpy"],
                    ]
                )
            filename = f"ebay_monthly_{year or 'all'}.csv"

        elif type == "procurement":
            # 仕入明細（消費税還付用）
            writer = csv.writer(output)
            writer.writerow(
                [
                    "日付",
                    "仕入先",
                    "商品名",
                    "仕入額(JPY)",
                    "消費税額(JPY)",
                    "送料(JPY)",
                    "その他(JPY)",
                    "合計(JPY)",
                    "SKU",
                    "ステータス",
                ]
            )
            procs = (
                db.query(crud.Procurement)
                .order_by(crud.Procurement.purchase_date)
                .all()
            )
            for p in procs:
                purchase_ym = (
                    p.purchase_date.strftime("%Y-%m") if p.purchase_date else ""
                )
                if year and not purchase_ym.startswith(year):
                    continue
                writer.writerow(
                    [
                        p.purchase_date.strftime("%Y-%m-%d") if p.purchase_date else "",
                        p.platform,
                        p.title,
                        p.purchase_price_jpy,
                        p.consumption_tax_jpy,
                        p.shipping_cost_jpy,
                        p.other_cost_jpy,
                        p.total_cost_jpy,
                        p.sku,
                        p.status,
                    ]
                )
            filename = f"ebay_procurement_{year or 'all'}.csv"
        else:
            raise HTTPException(400, f"Unknown export type: {type}")

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv; charset=utf-8-sig",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    finally:
        db.close()


# ── CPaaS送料CSVインポート ────────────────────────────────


@app.post("/api/shipping/import")
async def import_shipping_csv(request: Request):
    """CPaaS送料CSVをインポートし、追跡番号でSalesRecordと突き合わせる"""
    import csv
    import io

    form = await request.form()
    file = form.get("file")
    if not file:
        raise HTTPException(400, "No file uploaded")

    content = await file.read()
    # BOM付きUTF-8対応
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    db = get_db()
    try:
        matched = 0
        skipped = 0
        not_found = []
        matched_ids = set()  # 重複マッチ防止

        for row in reader:
            # CPaaSの「注文番号」= eBayのEMS/ePacket追跡番号
            order_number = row.get("注文番号", "").strip()
            tracking = row.get("追跡番号", "").strip()  # FedEx/DHL側の番号
            if not order_number and not tracking:
                skipped += 1
                continue

            # 送料系・関税系・合計を取得
            shipping_total = int(row.get("送料系", "0") or "0")
            customs_total = int(row.get("関税系", "0") or "0")
            carrier = row.get("キャリア", "").strip()
            product_name = row.get("商品名", "").strip()

            # 合計0の行（キャンセル等）はスキップ
            total = int(row.get("合計", "0") or "0")
            if total == 0:
                skipped += 1
                continue

            # 1) 注文番号（= eBay追跡番号）でSalesRecordを検索
            record = None
            if order_number:
                record = (
                    db.query(crud.SalesRecord)
                    .filter(crud.SalesRecord.tracking_number == order_number)
                    .first()
                )
            # 2) 追跡番号（FedEx/DHL）でも試行
            if not record and tracking:
                record = (
                    db.query(crud.SalesRecord)
                    .filter(crud.SalesRecord.tracking_number == tracking)
                    .first()
                )

            # 2) フォールバック: タイトル類似度マッチ（まだ送料未入力のもの）
            if not record and product_name:
                from difflib import SequenceMatcher

                candidates = (
                    db.query(crud.SalesRecord)
                    .filter(crud.SalesRecord.intl_shipping_cost_jpy == 0)
                    .filter(crud.SalesRecord.id.notin_(matched_ids))
                    .all()
                )
                best_ratio = 0
                best_candidate = None
                cp_lower = product_name[:60].lower()
                for c in candidates:
                    ratio = SequenceMatcher(
                        None, cp_lower, c.title[:60].lower()
                    ).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_candidate = c
                if best_ratio >= 0.7 and best_candidate:
                    record = best_candidate

            if not record:
                not_found.append(
                    {
                        "tracking": tracking,
                        "carrier": carrier,
                        "product": product_name[:60],
                        "total": total,
                    }
                )
                continue

            # 送料・キャリアを更新
            record.intl_shipping_cost_jpy = shipping_total
            if customs_total > 0:
                record.other_cost_jpy = customs_total
            if carrier:
                record.shipping_method = carrier

            # CPaaS追跡番号も保存（eBayのと異なる場合も参照用に）
            if tracking and not record.tracking_number:
                record.tracking_number = tracking

            # 利益再計算
            crud.calculate_net_profit(record)
            matched_ids.add(record.id)
            db.commit()
            matched += 1

        return JSONResponse(
            {
                "status": "ok",
                "matched": matched,
                "skipped": skipped,
                "not_found_count": len(not_found),
                "not_found": not_found[:20],  # 最大20件表示
            }
        )
    finally:
        db.close()


@app.post("/api/sales/sync-all")
async def sync_all_sales(request: Request):
    """Fulfillment API で全期間の注文を取得しDBに同期する"""
    from ebay_core.client import get_all_orders
    from ebay_core.exchange_rate import get_usd_to_jpy

    body = (
        await request.json()
        if request.headers.get("content-type", "").startswith("application/json")
        else {}
    )
    from_date = body.get("from_date", "")  # "YYYY-MM-DD"
    to_date = body.get("to_date", "")

    orders = get_all_orders(from_date=from_date, to_date=to_date)
    if not orders:
        return JSONResponse(
            {
                "status": "ok",
                "orders_fetched": 0,
                "new_records": 0,
                "skipped_existing": 0,
            }
        )

    rate = get_usd_to_jpy()
    db = get_db()
    new_count = 0
    skipped = 0

    try:
        for order in orders:
            order_id = order.get("order_id", "")
            tracking_number = order.get("tracking_number", "")
            shipping_carrier = order.get("shipping_carrier", "")
            buyer_name = order.get("buyer_name", "")
            buyer_country = order.get("buyer_country", "")
            created_time = order.get("created_time", "")

            for item in order["items"]:
                sku = item["sku"]
                sale_price = item["price_usd"]

                # 重複チェック: order_id + item_id
                existing = (
                    (
                        db.query(crud.SalesRecord)
                        .filter(
                            crud.SalesRecord.order_id == order_id,
                            crud.SalesRecord.item_id == item.get("item_id", ""),
                        )
                        .first()
                    )
                    if order_id
                    else None
                )

                # order_id未設定の旧レコードも SKU + 価格 でチェック
                if not existing:
                    existing = (
                        db.query(crud.SalesRecord)
                        .filter(
                            crud.SalesRecord.sku == sku,
                            crud.SalesRecord.sale_price_usd == sale_price,
                            crud.SalesRecord.order_id.in_(["", order_id]),
                        )
                        .first()
                    )

                if existing:
                    # 既存レコードの情報を補完
                    changed = False
                    if not existing.order_id and order_id:
                        existing.order_id = order_id
                        changed = True
                    if not existing.tracking_number and tracking_number:
                        existing.tracking_number = tracking_number
                        changed = True
                    if not existing.buyer_name and buyer_name:
                        existing.buyer_name = buyer_name
                        changed = True
                    if not existing.buyer_country and buyer_country:
                        existing.buyer_country = buyer_country
                        changed = True
                    if not existing.item_id and item.get("item_id"):
                        existing.item_id = item["item_id"]
                        changed = True
                    if not existing.shipping_method and shipping_carrier:
                        existing.shipping_method = shipping_carrier
                        changed = True

                    # sold_at修正
                    if created_time:
                        try:
                            correct_date = datetime.strptime(
                                created_time[:19], "%Y-%m-%dT%H:%M:%S"
                            )
                            if existing.sold_at != correct_date:
                                existing.sold_at = correct_date
                                changed = True
                        except ValueError:
                            pass

                    if changed:
                        db.commit()
                    skipped += 1
                    continue

                # sold_at解析
                sold_at = None
                if created_time:
                    try:
                        sold_at = datetime.strptime(
                            created_time[:19], "%Y-%m-%dT%H:%M:%S"
                        )
                    except ValueError:
                        pass

                # 仕入れ価格を取得（消費税は仕入金額から内税で分割済み）
                source_cost, shipping_cost, proc_tax = crud.get_latest_procurement_cost(
                    db, sku
                )
                source_cost = source_cost or 0
                shipping_cost = shipping_cost or 0
                proc_tax = proc_tax or 0

                # eBay手数料（Fulfillment APIから実額、なければ概算）
                ebay_fees = order.get("ebay_fees_usd") or round(
                    sale_price * EBAY_FEE_RATE, 2
                )
                payoneer_fee = round(sale_price * PAYONEER_FEE_RATE, 2)

                crud.add_sales_record(
                    db,
                    order_id=order_id,
                    item_id=item.get("item_id", ""),
                    sku=sku,
                    title=item["title"],
                    sale_price_usd=sale_price,
                    source_cost_jpy=source_cost,
                    shipping_cost_jpy=shipping_cost,
                    consumption_tax_jpy=proc_tax,
                    ebay_fees_usd=ebay_fees,
                    payoneer_fee_usd=payoneer_fee,
                    exchange_rate=rate,
                    tracking_number=tracking_number,
                    shipping_method=shipping_carrier,
                    buyer_name=buyer_name,
                    buyer_country=buyer_country,
                    **({"sold_at": sold_at} if sold_at else {}),
                )
                new_count += 1
    finally:
        db.close()

    return JSONResponse(
        {
            "status": "ok",
            "orders_fetched": len(orders),
            "new_records": new_count,
            "skipped_existing": skipped,
        }
    )


@app.post("/api/shipping/backfill-tracking")
async def backfill_tracking_numbers():
    """既存SalesRecordにeBay APIから追跡番号・注文情報をバックフィルする"""
    from ebay_core.client import get_recent_orders

    db = get_db()
    try:
        # 情報が不足しているレコードを取得
        empty_records = (
            db.query(crud.SalesRecord)
            .filter(
                (crud.SalesRecord.tracking_number == "")
                | (crud.SalesRecord.order_id == "")
                | (crud.SalesRecord.buyer_name == "")
            )
            .all()
        )
        if not empty_records:
            return JSONResponse(
                {
                    "status": "ok",
                    "message": "All records already up to date",
                    "updated": 0,
                }
            )

        # eBayから直近90日の注文を取得
        orders = get_recent_orders(days=90)

        # マッチ用マップ作成
        from collections import defaultdict

        # 1) order_id → order info
        order_by_id = {}
        # 2) (title, price) → order info
        order_by_item = {}
        # 3) sku → [order info, ...]（同SKU複数注文対応）
        orders_by_sku = defaultdict(list)
        # 既にDBにあるorder_idセット
        existing_oids = {r.order_id for r in empty_records if r.order_id}
        existing_oids.update(
            oid
            for (oid,) in db.query(crud.SalesRecord.order_id)
            .filter(crud.SalesRecord.order_id != "")
            .all()
        )

        for order in orders:
            oid = order.get("order_id", "")
            tn = order.get("tracking_number", "")
            carrier = order.get("shipping_carrier", "")
            buyer_name = order.get("buyer_name", "")
            buyer_country = order.get("buyer_country", "")
            created_time = order.get("created_time", "")

            info = {
                "order_id": oid,
                "tracking": tn,
                "carrier": carrier,
                "buyer_name": buyer_name,
                "buyer_country": buyer_country,
                "created_time": created_time,
            }

            if oid:
                order_by_id[oid] = info

            for item in order.get("items", []):
                info_with_item = {
                    **info,
                    "item_id": item.get("item_id", ""),
                    "sku": item.get("sku", ""),
                }
                key = (item.get("title", ""), item.get("price_usd", 0))
                order_by_item[key] = info_with_item

                sku = item.get("sku", "")
                if sku:
                    orders_by_sku[sku].append(info_with_item)

        updated = 0
        used_oids = set()  # 1つのorderを複数レコードに割り当てない

        for record in empty_records:
            info = None

            # 1) order_idでマッチ
            if record.order_id and record.order_id in order_by_id:
                info = order_by_id[record.order_id]
            else:
                # 2) タイトル+価格でマッチ
                key = (record.title, record.sale_price_usd)
                if key in order_by_item:
                    candidate = order_by_item[key]
                    if candidate.get("order_id") not in used_oids:
                        info = candidate

            # 3) SKUマッチ（同SKU複数注文はまだ使われていないorderを割り当て）
            if not info and record.sku and record.sku in orders_by_sku:
                for candidate in orders_by_sku[record.sku]:
                    coid = candidate.get("order_id", "")
                    if coid and coid not in used_oids and coid not in existing_oids:
                        info = candidate
                        break

            if not info:
                continue

            if info.get("order_id"):
                used_oids.add(info["order_id"])

            changed = False
            if not record.tracking_number and info.get("tracking"):
                record.tracking_number = info["tracking"]
                changed = True
            if not record.order_id and info.get("order_id"):
                record.order_id = info["order_id"]
                changed = True
            if not record.shipping_method and info.get("carrier"):
                record.shipping_method = info["carrier"]
                changed = True
            if not getattr(record, "buyer_name", "") and info.get("buyer_name"):
                record.buyer_name = info["buyer_name"]
                changed = True
            if not getattr(record, "buyer_country", "") and info.get("buyer_country"):
                record.buyer_country = info["buyer_country"]
                changed = True
            if not getattr(record, "item_id", "") and info.get("item_id"):
                record.item_id = info["item_id"]
                changed = True

            # sold_atが不正（全て同じ日時）なら修正
            created_time = info.get("created_time", "")
            if created_time:
                try:
                    correct_date = __import__("datetime").datetime.strptime(
                        created_time[:19], "%Y-%m-%dT%H:%M:%S"
                    )
                    if record.sold_at and record.sold_at != correct_date:
                        record.sold_at = correct_date
                        changed = True
                except ValueError:
                    pass

            if changed:
                updated += 1

        db.commit()
        return JSONResponse(
            {
                "status": "ok",
                "updated": updated,
                "total_empty": len(empty_records),
                "orders_fetched": len(orders),
            }
        )
    finally:
        db.close()


@app.get("/api/settings/screenshot-dir")
async def get_screenshot_dir():
    """スクリーンショット保存先を返す"""
    from config import SCREENSHOT_DIR

    return JSONResponse({"path": str(SCREENSHOT_DIR)})


@app.put("/api/settings/screenshot-dir")
async def set_screenshot_dir(request: Request):
    """スクリーンショット保存先を変更（.envに書き込み）"""
    body = await request.json()
    new_path = body.get("path", "").strip()
    if not new_path:
        raise HTTPException(400, "path is required")

    # .envに書き込み
    env_path = Path(__file__).parent / ".env"
    lines = []
    found = False
    if env_path.exists():
        lines = env_path.read_text().splitlines()
        for i, line in enumerate(lines):
            if line.startswith("SCREENSHOT_DIR="):
                lines[i] = f"SCREENSHOT_DIR={new_path}"
                found = True
                break
    if not found:
        lines.append(f"SCREENSHOT_DIR={new_path}")
    env_path.write_text("\n".join(lines) + "\n")

    return JSONResponse({"status": "updated", "path": new_path})


# ── 出品アシスタント ──────────────────────────────────────

import re as _re


def _extract_model_number(title: str) -> str:
    """英語eBayタイトルからブランド名+型番を抽出する。
    例: 'Pioneer DJ DDJ-SB3 Black DJ Controller 2-Channel' → 'Pioneer DDJ-SB3'
    ルール: 文字始まりの候補（DDJ-SB3等）を優先し、型番の直前にあるブランド名を付加。
    """
    tokens = _re.split(r"[\s/,()[\]]+", title)
    cleaned = [t.strip("-.") for t in tokens]
    candidates = [
        t
        for t in cleaned
        if len(t) >= 3
        and _re.search(r"[A-Za-z]", t)
        and (_re.search(r"\d", t) or _re.match(r"^[A-Z]{2,}-[A-Z]{1,}$", t))
    ]
    if not candidates:
        return ""
    letter_first = [c for c in candidates if c[0].isalpha()]
    pool = letter_first if letter_first else candidates
    model_num = max(pool, key=len)
    # 型番の前にあるブランド名（英字のみ・先頭大文字）を付加
    model_idx = cleaned.index(model_num) if model_num in cleaned else -1
    if model_idx > 0:
        brand = next(
            (t for t in tokens[:model_idx] if _re.match(r"^[A-Z][a-zA-Z]+$", t)),
            None,
        )
        if brand:
            return f"{brand} {model_num}"
    return model_num


async def _generate_jp_search_keyword(title: str) -> str:
    """Claude Haikuで英語タイトルから日本語検索キーワードを生成する。"""
    import asyncio
    import anthropic

    prompt = (
        "以下のeBay出品タイトルから、日本のフリマサイト（メルカリ・ヤフオク等）で"
        "検索するのに最適な日本語キーワードを1〜3語で返してください。"
        "キーワードのみを返し、説明・記号・改行は不要です。\n\n"
        f"タイトル: {title}"
    )

    def _call() -> str:
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=30,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()

    try:
        return await asyncio.wait_for(asyncio.to_thread(_call), timeout=10.0)
    except asyncio.TimeoutError:
        return ""
    except Exception as e:
        logger.warning(f"[search-jp] keyword生成失敗: {e}")
        return ""


@app.get("/listing-assistant", response_class=HTMLResponse)
async def listing_assistant_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="pages/listing_assistant.html", context={}
    )


@app.post("/api/listing-assistant/fetch-url")
async def listing_assistant_fetch_url(request: Request):
    """URLから商品情報を取得"""
    body = await request.json()
    url = body.get("url", "").strip()
    if not url:
        raise HTTPException(400, "url is required")
    from scrapers.product_detail import fetch_product_url

    result = await fetch_product_url(url)
    return JSONResponse(result)


@app.post("/api/listing-assistant/suggest-keywords")
async def listing_assistant_suggest_keywords(request: Request):
    """日本語タイトルからeBay英語検索キーワードを生成"""
    import asyncio
    import anthropic

    body = await request.json()
    title = body.get("title", "").strip()
    description = body.get("description", "").strip()[:500]
    platform = body.get("platform", "")

    if not title:
        raise HTTPException(400, "title is required")

    prompt = f"""Extract concise English search keywords for eBay from this Japanese product listing.

Japanese title: {title}
{"Platform: " + platform if platform else ""}
{"Description excerpt: " + description if description else ""}

Return ONLY a short English search phrase (4-8 words) suitable for eBay search.
Focus on: brand, model number, product type, key specs.
No explanation, no punctuation, just the keywords."""

    def _call_claude() -> str:
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=60,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()

    try:
        keywords = await asyncio.wait_for(
            asyncio.to_thread(_call_claude),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        keywords = ""
    except Exception as e:
        logger.warning(f"[suggest-keywords] Claude失敗: {e}")
        keywords = ""

    return JSONResponse({"keywords": keywords})


@app.post("/api/listing-assistant/demand")
async def listing_assistant_demand(request: Request):
    """eBay需要チェック"""
    import asyncio

    body = await request.json()
    title = body.get("title", "").strip()
    # JSから英語クエリが別途渡される場合はそちらを優先
    ebay_query = body.get("ebay_query", "").strip() or title
    price_jpy = int(body.get("price_jpy", 50000))
    if not ebay_query:
        raise HTTPException(400, "title is required")
    from research.demand import analyze_demand

    # analyze_demand は同期関数のため to_thread でイベントループをブロックしない
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                analyze_demand,
                query=ebay_query,
                max_source_price_jpy=price_jpy,
                limit=30,
            ),
            timeout=25.0,
        )
    except asyncio.TimeoutError:
        result = {
            "query": ebay_query,
            "status": "timeout",
            "message": "eBay検索がタイムアウトしました。後でもう一度お試しください。",
            "items_found": 0,
        }
    return JSONResponse(result)


@app.post("/api/listing-assistant/quick-price")
async def listing_assistant_quick_price(request: Request):
    """軽量需要チェック: Browse API(OAuth)でアクティブ出品を検索。Finding API不使用。

    アクティブ出品10件の中央値 + 利益率を計算して返す。
    """
    body = await request.json()
    query = (body.get("ebay_query") or body.get("title") or "").strip()
    purchase_price_jpy = int(body.get("purchase_price_jpy") or 0)
    if not query:
        return JSONResponse({"status": "no_results"})

    from ebay_core.client import search_ebay
    from ebay_core.exchange_rate import get_usd_to_jpy
    from config import EBAY_FEE_RATE, PAYONEER_FEE_RATE

    try:
        items = await asyncio.wait_for(
            asyncio.to_thread(search_ebay, query, 10),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        return JSONResponse({"status": "timeout", "items_found": 0})

    if not items:
        return JSONResponse({"status": "no_results", "items_found": 0})

    prices = sorted(float(i.get("price", 0)) for i in items if i.get("price", 0) > 0)
    if not prices:
        return JSONResponse({"status": "no_price_data", "items_found": len(items)})

    median_usd = prices[len(prices) // 2]
    rate = get_usd_to_jpy()
    source_usd = purchase_price_jpy / rate
    ebay_fee = median_usd * EBAY_FEE_RATE
    payoneer_fee = (median_usd - ebay_fee) * PAYONEER_FEE_RATE
    net_profit = median_usd - ebay_fee - payoneer_fee - source_usd - 20.0
    margin_pct = (net_profit / median_usd * 100) if median_usd > 0 else 0

    return JSONResponse(
        {
            "status": "ok",
            "median_usd": round(median_usd, 2),
            "net_profit_usd": round(net_profit, 2),
            "margin_pct": round(margin_pct, 1),
            "items_found": len(items),
            "exchange_rate": rate,
        }
    )


@app.post("/api/listing-assistant/calculate")
async def listing_assistant_calculate(request: Request):
    """価格・利益計算（目標利益率から逆算）"""
    body = await request.json()
    price_jpy = float(body.get("price_jpy", 0))
    tax_jpy = float(body.get("tax_jpy", 0))
    domestic_shipping_jpy = float(body.get("domestic_shipping_jpy", 0))
    # JSは international_shipping_usd で送信（intl_shipping_usd は後方互換）
    intl_shipping_usd = float(
        body.get("international_shipping_usd", body.get("intl_shipping_usd", 20.0))
    )
    target_margin_pct = float(body.get("target_margin_pct", 25.0))

    from ebay_core.exchange_rate import get_usd_to_jpy
    from config import EBAY_FEE_RATE, PAYONEER_FEE_RATE, CUSTOMS_DUTY_RATE

    rate = get_usd_to_jpy()
    customs_jpy = round(price_jpy * CUSTOMS_DUTY_RATE)
    total_cost_jpy = price_jpy + tax_jpy + domestic_shipping_jpy + customs_jpy
    domestic_cost_usd = total_cost_jpy / rate
    total_cost_usd = domestic_cost_usd + intl_shipping_usd

    # 手数料控除率: eBay 17% + Payoneer 2%（eBay控除後に適用）
    fee_deduction = EBAY_FEE_RATE + (1 - EBAY_FEE_RATE) * PAYONEER_FEE_RATE

    denom = 1 - fee_deduction - target_margin_pct / 100
    if denom <= 0.01:
        raise HTTPException(
            400, "目標利益率が高すぎます（手数料と合計が100%を超えます）"
        )

    recommended_price_usd = round(total_cost_usd / denom, 2)
    ebay_fee_usd = round(recommended_price_usd * EBAY_FEE_RATE, 2)
    payoneer_fee_usd = round(
        (recommended_price_usd - ebay_fee_usd) * PAYONEER_FEE_RATE, 2
    )
    profit_usd = round(
        recommended_price_usd - total_cost_usd - ebay_fee_usd - payoneer_fee_usd, 2
    )
    actual_margin_pct = (
        round(profit_usd / recommended_price_usd * 100, 1)
        if recommended_price_usd > 0
        else 0
    )

    return JSONResponse(
        {
            # 入力値をエコーバック（内訳テーブル表示用）
            "cost_jpy": round(price_jpy),
            "tax_jpy": round(tax_jpy),
            "domestic_shipping_jpy": round(domestic_shipping_jpy),
            "customs_jpy": customs_jpy,
            "international_shipping_usd": round(intl_shipping_usd, 2),
            # 集計値
            "total_cost_jpy": round(total_cost_jpy),
            "domestic_cost_usd": round(domestic_cost_usd, 2),
            "total_cost_usd": round(total_cost_usd, 2),
            "recommended_price_usd": recommended_price_usd,
            "ebay_fee_usd": ebay_fee_usd,
            "payoneer_fee_usd": payoneer_fee_usd,
            "profit_usd": profit_usd,
            "profit_jpy": round(profit_usd * rate),
            "actual_margin_pct": actual_margin_pct,
            "exchange_rate": round(rate, 1),
        }
    )


@app.post("/api/listing-assistant/generate")
async def listing_assistant_generate(request: Request):
    """AI出品情報生成"""
    body = await request.json()
    # JSは product_title で送信（title は後方互換）
    title = (body.get("product_title") or body.get("title") or "").strip()
    condition = body.get("condition", "")
    description = body.get("description", "")
    platform = body.get("platform", "")
    if not title:
        raise HTTPException(400, "title is required")

    from listing.generator import (
        apply_desc_template,
        generate_listing,
        load_desc_template,
    )

    product_name = title
    if platform:
        product_name = f"{title} (source: {platform})"

    result = await generate_listing(
        product_name=product_name,
        condition=condition,
        competitor_keywords=[],
    )

    titles = result.get("titles", [])
    best_title = titles[0]["title"] if titles else title
    raw_category = result.get("category_id", result.get("category_suggestion", ""))

    # AI が "Collectibles > ... > Cels" のようなパス文字列を返す場合があるため
    # 数値 leaf ID に解決する
    from ebay_core.client import resolve_category_id

    try:
        category_id = resolve_category_id(raw_category) or raw_category
    except Exception as _e:
        category_id = raw_category

    import re as _re

    def _strip_japanese(text: str) -> str:
        """Remove hiragana, katakana, and kanji from a string."""
        return _re.sub(r"[぀-ゟ゠-ヿ一-鿿㐀-䶿]", "", text).strip()

    # Strip Japanese from specs keys and values
    raw_specs = result.get("specs", {})
    specs = {
        _strip_japanese(str(k)): _strip_japanese(str(v))
        for k, v in raw_specs.items()
        if _strip_japanese(str(k))
    }

    description = _strip_japanese(result.get("description_html", ""))

    # Apply description template if one exists (e.g. listing/desc_templates/001.html)
    desc_template_name = body.get("desc_template", "001")
    tmpl_html = load_desc_template(desc_template_name)
    if tmpl_html:
        description = apply_desc_template(tmpl_html, description, title=best_title)

    return JSONResponse(
        {
            "title": best_title,
            "description": description,
            "item_specifics": specs,
            "category_id": category_id,
            "keywords": result.get("keywords", []),
        }
    )


@app.get("/api/listing-assistant/sold-no-stock")
async def listing_assistant_sold_no_stock(request: Request):
    """eShip在庫一覧から再仕入れ候補を返す。sold_out（実績あり在庫切れ）+ unlisted（未出品在庫切れ）"""
    import asyncio as _asyncio

    from comms.eship_inventory import fetch_reorder_candidates

    force = request.query_params.get("refresh") == "1"
    data = await _asyncio.get_event_loop().run_in_executor(
        None, lambda: fetch_reorder_candidates(force=force)
    )
    if data.get("error"):
        return JSONResponse({"error": data["error"]}, status_code=502)

    results = data["sold_out"] + data["unlisted"][:300]
    return JSONResponse(results)


@app.post("/api/listing-assistant/update-eship-source")
async def listing_assistant_update_eship_source(request: Request):
    """再仕入れ候補の仕入れ元URLとプラットフォームをeShipに反映し、在庫数を1にする"""
    body = await request.json()
    try:
        eship_id = int(body.get("eship_id", 0))
    except (ValueError, TypeError):
        raise HTTPException(400, "eship_id must be an integer")
    source_url = (body.get("source_url") or "").strip()
    item_title = (body.get("item_title") or "").strip()
    platform = (body.get("platform") or "").strip()

    if not eship_id or not source_url:
        raise HTTPException(400, "eship_id and source_url are required")

    from comms.eship_client import update_eship_source

    result = await update_eship_source(
        eship_id=eship_id,
        item_title=item_title,
        source_url=source_url,
        platform=platform,
    )
    status_code = 200 if result.get("status") == "ok" else 502
    return JSONResponse(result, status_code=status_code)


@app.post("/api/listing-assistant/search-jp")
async def listing_assistant_search_jp(request: Request):
    """メルカリ・ヤフオク・Yahoo!フリマを並列検索する"""
    body = await request.json()
    title = body.get("title", "").strip()
    try:
        purchase_price_jpy = int(body.get("purchase_price_jpy", 0) or 0)
    except (ValueError, TypeError):
        purchase_price_jpy = 0

    if not title:
        raise HTTPException(400, "title is required")

    # 上限価格: リクエスト側で指定可能。未指定の場合は仕入れ価格の3倍（最低5,000円）
    try:
        max_price_jpy_override = body.get("max_price_jpy")
        if max_price_jpy_override is not None:
            max_price_jpy = int(max_price_jpy_override)
        else:
            max_price_jpy = max(int(purchase_price_jpy * 3), 5000)
    except (ValueError, TypeError):
        max_price_jpy = max(int(purchase_price_jpy * 3), 5000)

    # キーワード決定: 型番 → Haiku生成 → タイトルそのまま
    keyword = _extract_model_number(title)
    if not keyword:
        keyword = await _generate_jp_search_keyword(title)
    if not keyword:
        keyword = title[:50]

    import urllib.parse as _up

    enc = _up.quote(keyword, safe="")
    return JSONResponse(
        {
            "keyword": keyword,
            "max_price_jpy": max_price_jpy,
            "urls": {
                "ヤフオク": f"https://auctions.yahoo.co.jp/search/search/{enc}/0/?n=50",
                "メルカリ": f"https://jp.mercari.com/search?keyword={enc}&status=on_sale",
                "Yahoo!フリマ": f"https://paypayfleamarket.yahoo.co.jp/search/{enc}",
                "ラクマ": f"https://fril.jp/search/{enc}",
            },
        }
    )


# ローカルMacで動くスクレイパー検索サーバ (autossh で VPS:5759 にトンネル)
LOCAL_SEARCH_URL = os.getenv("LOCAL_SEARCH_URL", "http://127.0.0.1:5759")


@app.post("/api/listing-assistant/search-candidates")
async def listing_assistant_search_candidates(request: Request):
    """メルカリ・ヤフオク・Yahoo!フリマの実際の出品データを並列取得する

    ローカルMac側の local/server.py に委譲する (autossh tunnel 経由)。
    スクレイパーは VPS IP がブロックされているためローカル実行が必須。
    失敗時は search-jp 同等の検索URLにフォールバックする。
    """
    import httpx
    import urllib.parse as _up

    body = await request.json()
    title = body.get("title", "").strip()
    try:
        purchase_price_jpy = int(body.get("purchase_price_jpy", 0) or 0)
    except (ValueError, TypeError):
        purchase_price_jpy = 0
    try:
        ebay_price_usd = float(body.get("ebay_price_usd", 0) or 0)
    except (ValueError, TypeError):
        ebay_price_usd = 0.0
    try:
        limit = int(body.get("limit", 5))
    except (ValueError, TypeError):
        limit = 5
    junk_ok = bool(body.get("junk_ok", False))

    if not title:
        raise HTTPException(400, "title is required")

    try:
        max_price_jpy_override = body.get("max_price_jpy")
        if max_price_jpy_override is not None:
            max_price_jpy = int(max_price_jpy_override)
        elif purchase_price_jpy > 0:
            max_price_jpy = max(int(purchase_price_jpy * 3), 5000)
        elif ebay_price_usd > 0:
            # eBay売値の50%を仕入れ上限の目安（為替155円固定）
            max_price_jpy = max(int(ebay_price_usd * 155 * 0.5), 5000)
        else:
            max_price_jpy = 50000
    except (ValueError, TypeError):
        max_price_jpy = 50000

    keyword = _extract_model_number(title)
    if not keyword:
        keyword = await _generate_jp_search_keyword(title)
    if not keyword:
        keyword = title[:50]

    enc = _up.quote(keyword, safe="")
    fallback_urls = {
        "ヤフオク": f"https://auctions.yahoo.co.jp/search/search/{enc}/0/?n=50",
        "メルカリ": f"https://jp.mercari.com/search?keyword={enc}&status=on_sale",
        "Yahoo!フリマ": f"https://paypayfleamarket.yahoo.co.jp/search/{enc}",
        "ラクマ": f"https://fril.jp/search/{enc}",
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            resp = await client.post(
                f"{LOCAL_SEARCH_URL}/search",
                json={
                    "keyword": keyword,
                    "max_price_jpy": max_price_jpy,
                    "limit": limit,
                    "junk_ok": junk_ok,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning(
            f"local search server unreachable: {e!r} — falling back to URL list"
        )
        return JSONResponse(
            {
                "ok": False,
                "fallback": True,
                "error": str(e),
                "keyword": keyword,
                "max_price_jpy": max_price_jpy,
                "items": [],
                "by_platform": {},
                "urls": fallback_urls,
            }
        )

    return JSONResponse(
        {
            "ok": True,
            "fallback": False,
            "keyword": keyword,
            "max_price_jpy": max_price_jpy,
            "items": data.get("items", []),
            "by_platform": data.get("by_platform", {}),
            "errors": data.get("errors", {}),
            "urls": fallback_urls,
        }
    )


@app.post("/api/listing-assistant/submit/ledger")
async def listing_assistant_submit_ledger(request: Request):
    """仕入れ台帳に登録"""
    body = await request.json()
    product = body.get("product", {})
    source_url = body.get("source_url", "")
    price_usd = float(body.get("price_usd", 0))
    calc = body.get("calc", {})

    price_jpy = int(product.get("price_jpy", 0))
    tax_jpy = round(price_jpy * 0.10)
    platform = product.get("platform", "")
    title = product.get("title", "")
    seller_id = product.get("seller_id", "")
    image_url = product.get("image_url", "")
    domestic_shipping_jpy = int(calc.get("domestic_shipping_jpy", 0))

    db = get_db()
    try:
        proc = crud.add_procurement(
            db,
            title=title,
            platform=platform,
            url=source_url,
            purchase_price_jpy=price_jpy,
            consumption_tax_jpy=tax_jpy,
            shipping_cost_jpy=domestic_shipping_jpy,
            seller_id=seller_id,
            status="purchased",
            ebay_selling_price_usd=price_usd,
            image_url=image_url,
        )
        return JSONResponse(
            {"ok": True, "id": proc.id, "stock_number": proc.stock_number or ""}
        )
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        db.close()


@app.post("/api/listing-assistant/submit/eship")
async def listing_assistant_submit_eship(request: Request):
    """eShipに仕入れ品を登録 (eBay出品後の ItemID を ebay_item_id に紐付け可)"""
    body = await request.json()
    product = body.get("product", {})
    source_url = body.get("source_url", "")
    ebay_title = body.get("ebay_title", product.get("title", ""))
    price_usd = float(body.get("price_usd", 0))
    calc = body.get("calc", {})

    price_jpy = int(product.get("price_jpy", 0))
    tax_jpy = round(price_jpy * 0.10)
    platform = product.get("platform", "")
    image_url = product.get("image_url", "")
    domestic_shipping_jpy = int(calc.get("domestic_shipping_jpy", 0))
    stock_number = body.get("stock_number", "")
    ebay_item_id = body.get("ebay_item_id", "")

    from comms.eship_client import create_eship_item

    try:
        result = await create_eship_item(
            title=ebay_title,
            supplier_url=source_url,
            purchase_price=price_jpy + tax_jpy + domestic_shipping_jpy,
            platform=platform,
            selling_price_usd=price_usd,
            sku=stock_number,
            ebay_item_id=ebay_item_id,
            image_url=image_url,
        )
        if result.get("status") == "ok":
            return JSONResponse(
                {"ok": True, "inventory_id": result.get("inventory_id", "")}
            )
        raise HTTPException(500, result.get("message", "eShip登録失敗"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/listing-assistant/submit/ebay-publish")
async def listing_assistant_submit_ebay_publish(request: Request):
    """eBay実出品: ギャラリー画像を全枚 white-bg → EPS upload → 公開 → ItemID 返却。"""
    body = await request.json()
    product = body.get("product", {})
    ebay_title = body.get("ebay_title", product.get("title", ""))
    description = body.get("description", "")
    category_id = body.get("category_id", "")
    condition = body.get("condition", "USED_VERY_GOOD")
    item_specifics = body.get("item_specifics", {})
    price_usd = float(body.get("price_usd", 0))
    stock_number = body.get("stock_number", "")

    # eBay title hard limit = 80 chars. AI が稀に超過するためサーバ側で語境界で安全網
    if ebay_title and len(ebay_title) > 80:
        original_len = len(ebay_title)
        trimmed = ebay_title[:80].rstrip()
        last_space = trimmed.rfind(" ")
        if 60 <= last_space < 80:
            trimmed = trimmed[:last_space].rstrip()
        ebay_title = trimmed.rstrip(",.-:;")
        logger.warning(f"ebay_title truncated: {original_len}→{len(ebay_title)} chars")

    image_urls = product.get("image_urls") or []
    if not image_urls and product.get("image_url"):
        image_urls = [product["image_url"]]
    if not image_urls:
        raise HTTPException(400, "画像URLが見つかりません")

    # eBay カテゴリID は必須（数値の leaf category）
    category_id = (category_id or "").strip()
    if category_id and not category_id.isdigit():
        # パス文字列で来た場合は Taxonomy で leaf ID に解決
        from ebay_core.client import resolve_category_id

        resolved = resolve_category_id(category_id)
        if resolved:
            category_id = resolved
    if not category_id or not category_id.isdigit():
        raise HTTPException(
            400,
            f"eBay カテゴリID が未入力または解決不能です (category_id={category_id!r}). "
            "Step 3 で leaf category の数値ID（例: 112529）を入力してください。",
        )

    from ebay_core.client import (
        create_inventory_item,
        create_offer,
        publish_offer,
        upload_image_bytes,
    )
    from listing.generator import DEFAULT_CONDITION_DESCRIPTION
    from listing.image_utils import whitebg_many

    # SKU 既定: roki + JST YYYYMMDDHHMM (Roki さん命名規約)
    JST = timezone(timedelta(hours=9))
    sku = stock_number or f"roki{datetime.now(JST).strftime('%Y%m%d%H%M')}"

    # フロントから description が再送される時点でテンプレ未置換だった場合に備えた safety net
    if ebay_title and description:
        description = description.replace("[[title]]", ebay_title)

    condition_description = (
        body.get("condition_description") or DEFAULT_CONDITION_DESCRIPTION
    )

    # 1) White-bg every gallery image in parallel
    wb_results = await whitebg_many(image_urls)
    eps_urls: list[str] = []
    images_failed: list[dict] = []
    for idx, (src_url, jpeg_bytes, err) in enumerate(wb_results):
        if err or not jpeg_bytes:
            images_failed.append({"url": src_url, "stage": "whitebg", "error": err})
            continue
        # 2) Upload each white-bg JPEG to eBay EPS
        up = await asyncio.to_thread(
            upload_image_bytes, jpeg_bytes, f"{sku}_{idx + 1}.jpg"
        )
        if up.get("success") and up.get("url"):
            eps_urls.append(up["url"])
        else:
            images_failed.append(
                {"url": src_url, "stage": "eps", "error": up.get("error")}
            )

    if not eps_urls:
        raise HTTPException(
            500,
            f"画像処理に全て失敗しました: {images_failed[:3]}",
        )

    # 3) Create inventory item with EPS URLs
    inv_result = create_inventory_item(
        sku=sku,
        product={
            "title": ebay_title,
            "description": description,
            "aspects": item_specifics,
            "imageUrls": eps_urls,
        },
        condition=condition,
        condition_description=condition_description,
    )
    if not inv_result.get("success"):
        raise HTTPException(
            500, inv_result.get("error", "Inventory item creation failed")
        )

    # 仕入元がヤフオクの場合のみ M(YO) Speed Pak Expedited policy を使う
    # (env var で上書き可。未設定なら create_offer() のデフォルト M Speed Pak Expedited)
    source_platform = (product.get("platform") or "").strip()
    source_url_for_detect = body.get("source_url") or product.get("product_url") or ""
    if not source_platform and source_url_for_detect:
        from scrapers.product_detail import _detect_platform

        source_platform = _detect_platform(source_url_for_detect)
    fulfillment_policy_id = ""
    if source_platform == "ヤフオク":
        fulfillment_policy_id = os.environ.get(
            "YAHOO_FULFILLMENT_POLICY_ID", "250756481010"
        )
        logger.info(
            f"仕入元=ヤフオク → fulfillment_policy_id={fulfillment_policy_id} "
            "(M(YO) Speed Pak Expedited)"
        )

    # 4) Create offer (draft)
    offer_result = create_offer(
        sku=sku,
        category_id=category_id,
        price_usd=price_usd,
        condition=condition,
        fulfillment_policy_id=fulfillment_policy_id,
        return_policy_id="",
        payment_policy_id="",
        listing_description=description,
    )
    if not offer_result.get("success"):
        raise HTTPException(500, offer_result.get("error", "Offer creation failed"))

    offer_id = offer_result.get("offer_id", "")

    # 5) Publish offer to get the real ItemID (listing_id)
    pub_result = await asyncio.to_thread(publish_offer, offer_id)
    if not pub_result.get("success"):
        raise HTTPException(
            500,
            f"Offer 公開失敗 (offer_id={offer_id}): {pub_result.get('error', '')}",
        )

    listing_id = pub_result.get("listing_id", "")

    # 6) Promoted Listings General 2% に自動付与（失敗しても出品成功扱い）
    promoted_listings: dict = {"enabled": True, "status": "skipped"}
    if listing_id:
        try:
            from ebay_core.client import (
                create_promoted_listing_ad,
                find_general_campaign_id,
            )

            campaign_id = await asyncio.to_thread(find_general_campaign_id, "EBAY_US")
            if not campaign_id:
                promoted_listings = {
                    "enabled": True,
                    "status": "no_campaign",
                    "warning": (
                        "eBay 側に ACTIVE な General (COST_PER_SALE) "
                        "Promoted Listings キャンペーンが見つかりません。"
                        "Seller Hub で General キャンペーンを 1 つ作成してください。"
                    ),
                }
            else:
                pl_result = await asyncio.to_thread(
                    create_promoted_listing_ad, campaign_id, listing_id, 2.0
                )
                if pl_result.get("success"):
                    promoted_listings = {
                        "enabled": True,
                        "status": "ok",
                        "campaign_id": campaign_id,
                        "ad_id": pl_result.get("ad_id", ""),
                        "bid_percentage": 2.0,
                    }
                else:
                    promoted_listings = {
                        "enabled": True,
                        "status": "failed",
                        "campaign_id": campaign_id,
                        "warning": (
                            f"Promoted Listings 追加失敗: {pl_result.get('error', '')}"
                        ),
                    }
        except Exception as e:
            logger.exception("Promoted Listings 自動付与でエラー")
            promoted_listings = {
                "enabled": True,
                "status": "error",
                "warning": f"Promoted Listings 例外: {e}",
            }

    return JSONResponse(
        {
            "ok": True,
            "item_id": listing_id,
            "offer_id": offer_id,
            "sku": sku,
            "ebay_listing_url": (
                f"https://www.ebay.com/itm/{listing_id}" if listing_id else ""
            ),
            "images_processed": len(eps_urls),
            "images_failed": images_failed,
            "promoted_listings": promoted_listings,
        }
    )


# ── eBayディスカバリー ──────────────────────────────────────


@app.get("/discover", response_class=HTMLResponse)
async def discover_redirect():
    return RedirectResponse(url="/research", status_code=301)


@app.post("/api/discover/search")
async def discover_search(request: Request):
    """eBayで売れ筋商品を検索し、未経験の商品をスコアリングして返す"""
    import re
    from ebay_core.client import search_ebay_discover
    from ebay_core.exchange_rate import get_usd_to_jpy

    body = await request.json() if await request.body() else {}
    keyword = body.get("keyword", "Japan").strip()
    category = body.get("category", "").strip()
    limit = min(int(body.get("limit", 50)), 200)
    price_min = float(body.get("price_min", 0))
    price_max = float(body.get("price_max", 0))
    condition_ids = body.get("condition_ids", "")  # "3000" or "1000,3000"

    if not keyword:
        keyword = "Japan"

    # eBay検索（フィルタ付き）
    try:
        data = search_ebay_discover(
            keyword,
            limit=limit,
            category_id=category,
            price_min=price_min,
            price_max=price_max,
            condition_ids=condition_ids,
        )
        items = data["items"]
        market_total = data["total"]  # eBay上の総ヒット数（需要指標）
    except Exception as e:
        logger.error(f"Discover search failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

    if not items:
        return JSONResponse(
            {
                "results": [],
                "keyword": keyword,
                "total": 0,
                "market_total": 0,
                "message": "検索結果なし",
            }
        )

    # 過去の自分の売上タイトルを取得（既知商品フィルタ用）
    from database.models import SalesRecord, Listing

    db = get_db()
    try:
        all_sales = db.query(SalesRecord).all()
        own_titles = {(s.title or "").lower() for s in all_sales}

        all_listings = db.query(Listing).all()
        own_listing_titles = {(l.title or "").lower() for l in all_listings}

        known_titles = own_titles | own_listing_titles

        rate = get_usd_to_jpy()

        # 需要レベル: 総ヒット数から算出
        if market_total >= 5000:
            demand_level = "high"
            demand_base = 35
        elif market_total >= 1000:
            demand_level = "medium"
            demand_base = 25
        elif market_total >= 200:
            demand_level = "low"
            demand_base = 15
        else:
            demand_level = "very_low"
            demand_base = 5

        results = []
        for item in items:
            title_lower = item["title"].lower()

            # 既知商品判定
            title_words = set(re.findall(r"[a-z0-9]+", title_lower))
            is_known = False
            for known in known_titles:
                known_words = set(re.findall(r"[a-z0-9]+", known))
                overlap = title_words & known_words
                if len(overlap) >= 4 and len(overlap) >= len(title_words) * 0.5:
                    is_known = True
                    break

            price_usd = item["price"]
            sold_qty = item["sold_quantity"]

            # スコアリング: 需要(35) + 価格帯(30) + 新規性(25) + 売れ数ボーナス(10)
            # 需要: eBay総ヒット数ベース
            d_score = demand_base
            # 価格帯: $50-$500がスイートスポット
            if 50 <= price_usd <= 500:
                p_score = 30
            elif 30 <= price_usd < 50 or 500 < price_usd <= 1000:
                p_score = 20
            elif price_usd > 1000:
                p_score = 15
            else:
                p_score = 10
            # 新規性
            n_score = 25 if not is_known else 0
            # マルチ数量で売れ実績があればボーナス
            s_score = min(10, sold_qty * 2)
            score = round(d_score + p_score + n_score + s_score)

            results.append(
                {
                    "title": item["title"],
                    "price_usd": price_usd,
                    "price_jpy": round(price_usd * rate),
                    "sold_quantity": sold_qty,
                    "condition": item["condition"],
                    "image_url": item["image_url"],
                    "item_url": item["item_url"],
                    "seller": item["seller"],
                    "seller_feedback": item.get("seller_feedback", 0),
                    "category_id": item["category_id"],
                    "item_location": item.get("item_location", ""),
                    "is_known": is_known,
                    "score": score,
                }
            )

        # スコア順
        results.sort(key=lambda x: x["score"], reverse=True)

        return JSONResponse(
            {
                "results": results,
                "keyword": keyword,
                "total": len(results),
                "market_total": market_total,
                "demand_level": demand_level,
                "new_items": sum(1 for r in results if not r["is_known"]),
                "exchange_rate": rate,
            }
        )
    finally:
        db.close()


@app.post("/api/discover/estimate")
async def discover_estimate(request: Request):
    """仕入れ価格を入力して利益シミュレーション"""
    from ebay_core.exchange_rate import get_usd_to_jpy

    body = await request.json()
    sell_price_usd = float(body.get("sell_price_usd", 0))
    source_cost_jpy = int(body.get("source_cost_jpy", 0))

    if sell_price_usd <= 0:
        return JSONResponse({"error": "sell_price_usd is required"}, status_code=400)

    rate = get_usd_to_jpy()
    cost_usd = source_cost_jpy / rate if rate > 0 else 0
    ebay_fee = sell_price_usd * EBAY_FEE_RATE
    payoneer_fee = sell_price_usd * PAYONEER_FEE_RATE
    shipping_usd = float(body.get("shipping_usd", 30))  # デフォルト送料$30

    profit_usd = sell_price_usd - cost_usd - ebay_fee - payoneer_fee - shipping_usd
    profit_jpy = round(profit_usd * rate)
    margin = round((profit_usd / sell_price_usd * 100) if sell_price_usd > 0 else 0, 1)

    return JSONResponse(
        {
            "sell_price_usd": sell_price_usd,
            "source_cost_jpy": source_cost_jpy,
            "source_cost_usd": round(cost_usd, 2),
            "ebay_fee_usd": round(ebay_fee, 2),
            "payoneer_fee_usd": round(payoneer_fee, 2),
            "shipping_usd": shipping_usd,
            "profit_usd": round(profit_usd, 2),
            "profit_jpy": profit_jpy,
            "margin_pct": margin,
            "exchange_rate": rate,
        }
    )


# ── セラー分析 ──────────────────────────────────────────


@app.post("/api/discover/seller-analysis")
async def seller_analysis(request: Request):
    """指定セラーの出品を分析して商品構成・価格帯・キーワード等を返す"""
    import re
    from collections import Counter
    from ebay_core.client import search_ebay_discover
    from ebay_core.exchange_rate import get_usd_to_jpy

    body = await request.json()
    seller_name = body.get("seller", "").strip()
    if not seller_name:
        return JSONResponse({"error": "seller is required"}, status_code=400)

    # Browse API でセラーの出品を取得（category_ids=0でバイアスなし全件取得）
    try:
        from ebay_core.client import _browse_headers, EBAY_API_BASE
        import requests as req

        headers = _browse_headers()
        url = f"{EBAY_API_BASE}/buy/browse/v1/item_summary/search"

        params = {
            "category_ids": "0",
            "limit": 200,
            "fieldgroups": "EXTENDED",
            "filter": f"sellers:{{{seller_name}}}",
        }
        resp = req.get(url, headers=headers, params=params, timeout=20)
        if resp.status_code != 200:
            err_msg = (
                resp.json()
                .get("errors", [{}])[0]
                .get("message", f"HTTP {resp.status_code}")
            )
            return JSONResponse({"error": err_msg}, status_code=502)
        data = resp.json()
        items_raw = data.get("itemSummaries", [])
        total_listings = data.get("total", len(items_raw))

    except Exception as e:
        logger.error(f"Seller analysis failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

    if not total_listings:
        total_listings = len(items_raw)

    if not items_raw:
        return JSONResponse(
            {"error": f"No listings found for seller '{seller_name}'"}, status_code=404
        )

    rate = get_usd_to_jpy()

    # 集計
    prices = []
    categories = Counter()
    conditions = Counter()
    keywords = Counter()
    items_out = []

    for item in items_raw:
        price = float(item.get("price", {}).get("value", 0))
        prices.append(price)

        # カテゴリ: 上位カテゴリ（2番目）を優先、なければリーフ
        cats = item.get("categories", [])
        cat_id = ""
        cat_label = "Other"
        if len(cats) >= 2:
            cat_id = cats[1].get("categoryId", "")
            cat_label = cats[1].get("categoryName", "Other")
        elif cats:
            cat_id = cats[0].get("categoryId", "")
            cat_label = cats[0].get("categoryName", "Other")
        categories[cat_label] += 1

        # 状態
        cond = item.get("condition", "Unknown")
        conditions[cond] += 1

        # タイトルキーワード（英語3文字以上、ストップワード除外）
        title = item.get("title", "")
        stop_words = {
            "the",
            "and",
            "for",
            "with",
            "from",
            "new",
            "used",
            "vintage",
            "rare",
            "japan",
            "japanese",
            "free",
            "shipping",
            "tested",
            "working",
        }
        words = re.findall(r"[a-zA-Z]{3,}", title.lower())
        for w in words:
            if w not in stop_words:
                keywords[w] += 1

        items_out.append(
            {
                "title": title,
                "price_usd": price,
                "price_jpy": round(price * rate),
                "condition": cond,
                "category": cat_label,
                "category_id": cat_id,
                "image_url": item.get("image", {}).get("imageUrl", ""),
                "item_url": item.get("itemWebUrl", ""),
            }
        )

    prices.sort()
    avg_price = round(sum(prices) / len(prices), 2) if prices else 0
    median_price = round(prices[len(prices) // 2], 2) if prices else 0

    # 価格帯分布
    price_ranges = {
        "$0-50": 0,
        "$50-200": 0,
        "$200-500": 0,
        "$500-1000": 0,
        "$1000+": 0,
    }
    for p in prices:
        if p < 50:
            price_ranges["$0-50"] += 1
        elif p < 200:
            price_ranges["$50-200"] += 1
        elif p < 500:
            price_ranges["$200-500"] += 1
        elif p < 1000:
            price_ranges["$500-1000"] += 1
        else:
            price_ranges["$1000+"] += 1

    # 自分の出品と比較（Gap Analysis）
    from database.models import Listing

    db = get_db()
    try:
        my_listings = db.query(Listing).all()
        my_categories = Counter()
        for l in my_listings:
            my_categories[l.category_id or "Other"] += 1

        # セラーのカテゴリで自分にないもの
        gaps = []
        for cat, count in categories.most_common(10):
            pct = round(count / len(items_raw) * 100)
            # 自分のカテゴリにマッチするか（名前ベースで簡易チェック）
            my_count = 0
            for my_cat, my_cnt in my_categories.items():
                if cat.lower() in str(my_cat).lower():
                    my_count = my_cnt
                    break
            gaps.append(
                {
                    "category": cat,
                    "seller_count": count,
                    "seller_pct": pct,
                    "my_count": my_count,
                }
            )
    finally:
        db.close()

    return JSONResponse(
        {
            "seller": seller_name,
            "total_listings": total_listings,
            "fetched": len(items_raw),
            "avg_price_usd": avg_price,
            "median_price_usd": median_price,
            "min_price_usd": round(prices[0], 2) if prices else 0,
            "max_price_usd": round(prices[-1], 2) if prices else 0,
            "categories": [
                {"name": k, "count": v, "pct": round(v / len(items_raw) * 100)}
                for k, v in categories.most_common(15)
            ],
            "conditions": [
                {"name": k, "count": v, "pct": round(v / len(items_raw) * 100)}
                for k, v in conditions.most_common()
            ],
            "price_ranges": price_ranges,
            "top_keywords": [
                {"word": k, "count": v} for k, v in keywords.most_common(25)
            ],
            "gap_analysis": gaps,
            "items": items_out[:50],  # 上位50件のみUIに返す
            "exchange_rate": rate,
        }
    )


# ── 仕入れサイト巡回 ──────────────────────────────────────


@app.post("/api/discover/source-search")
async def source_search(request: Request):
    """商品タイトルからメルカリ・ヤフオク・ラクマの検索URL＋相場推定を返す"""
    import re
    import urllib.parse

    body = await request.json()
    title = body.get("title", "").strip()
    if not title:
        return JSONResponse({"error": "title is required"}, status_code=400)

    # タイトルから検索キーワード抽出
    # 型番・ブランド名（英数字メイン）を優先的に抽出
    words = re.findall(r"[A-Za-z0-9][\w\-]*[A-Za-z0-9]", title)
    # ストップワード除外
    stop = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "new",
        "used",
        "vintage",
        "rare",
        "japan",
        "japanese",
        "free",
        "shipping",
        "tested",
        "working",
        "pre",
        "owned",
        "excellent",
        "good",
        "condition",
        "great",
        "oem",
        "genuine",
        "authentic",
        "original",
        "box",
    }
    filtered = [w for w in words if w.lower() not in stop and len(w) >= 2]

    # 最大5語を検索クエリに
    query_words = filtered[:5]
    query = " ".join(query_words)

    if not query:
        query = title[:40]

    encoded = urllib.parse.quote(query)

    # 各サイトの検索URL生成
    sources = [
        {
            "site": "メルカリ",
            "url": f"https://jp.mercari.com/search?keyword={encoded}",
            "icon": "🟡",
        },
        {
            "site": "ヤフオク",
            "url": f"https://auctions.yahoo.co.jp/search/search?p={encoded}&va={encoded}&exflg=1&b=1&n=50",
            "icon": "🔴",
        },
        {
            "site": "ヤフオク（落札相場）",
            "url": f"https://auctions.yahoo.co.jp/closedsearch/closedsearch?p={encoded}&va={encoded}&exflg=1&b=1&n=50",
            "icon": "🔴",
        },
        {
            "site": "ラクマ",
            "url": f"https://fril.jp/search/{encoded}",
            "icon": "🟢",
        },
        {
            "site": "Amazon.co.jp",
            "url": f"https://www.amazon.co.jp/s?k={encoded}",
            "icon": "🟠",
        },
    ]

    return JSONResponse(
        {
            "title": title,
            "search_query": query,
            "sources": sources,
        }
    )


# ── Shopify Webhook ───────────────────────────────────────


def verify_shopify_webhook(body: bytes, signature: str, secret: str) -> bool:
    """Shopify webhookのHMAC-SHA256署名を検証する"""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    computed = base64.b64encode(digest).decode()
    return hmac.compare_digest(computed, signature)


@app.post("/shopify/webhook/order-created")
async def shopify_order_created(request: Request):
    """Shopifyで注文が発生したとき — 対応するeBay在庫とShopify商品を閉じる"""
    body = await request.body()
    signature = request.headers.get("X-Shopify-Hmac-Sha256", "")

    if not verify_shopify_webhook(body, signature, SHOPIFY_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid Shopify webhook signature")

    payload = json.loads(body)
    line_items = payload.get("line_items", [])

    db = get_db()
    try:
        for item in line_items:
            sku = item.get("sku", "")
            if not sku:
                continue
            listing = db.query(Listing).filter_by(sku=sku).first()
            if not listing:
                continue
            # eBay在庫を0に
            listing.quantity = 0
            # Shopify商品も削除
            if listing.shopify_product_id:
                from shopify.client import ShopifyClient

                client = ShopifyClient()
                try:
                    await client.delete_product(listing.shopify_product_id)
                except Exception:
                    logger.warning(f"Failed to delete Shopify product for {sku}")
                listing.shopify_product_id = None
                listing.shopify_variant_id = None
            db.commit()
            logger.info(f"Webhook: closed eBay+Shopify for sold SKU {sku}")
    finally:
        db.close()

    return {"status": "ok"}


# ── ヘルスチェック ────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ebay-agent-hub"}


# ── Overview ダッシュボード API ──────────────────────────


@app.get("/api/overview/achievement")
async def overview_achievement():
    """当月の達成状況（目標 vs 実績・ペース予測）"""
    from database.crud import get_monthly_achievement

    db = get_db()
    try:
        today = datetime.now()
        return JSONResponse(get_monthly_achievement(db, today.year, today.month))
    finally:
        db.close()


@app.get("/api/overview/calendar")
async def overview_calendar():
    """当月の日別売上データ（カレンダーヒートマップ用）"""
    from database.crud import get_monthly_calendar

    db = get_db()
    try:
        today = datetime.now()
        return JSONResponse(get_monthly_calendar(db, today.year, today.month))
    finally:
        db.close()


@app.get("/api/overview/calendar_prev")
async def overview_calendar_prev():
    """前月の日別売上データ（月別累計チャート用）"""
    from database.crud import get_monthly_calendar
    from datetime import timedelta

    db = get_db()
    try:
        first_of_month = datetime.now().replace(day=1)
        prev = first_of_month - timedelta(days=1)
        return JSONResponse(get_monthly_calendar(db, prev.year, prev.month))
    finally:
        db.close()


@app.get("/api/overview/alerts")
async def overview_alerts():
    """要対応件数サマリー（在庫切れ・未読・価格アラート）"""
    from database.crud import get_overview_alerts

    db = get_db()
    try:
        return JSONResponse(get_overview_alerts(db))
    finally:
        db.close()


@app.get("/api/overview/pace")
async def overview_pace():
    """今日の売上・前月同日比・日次平均"""
    from database.crud import get_overview_pace

    db = get_db()
    try:
        return JSONResponse(get_overview_pace(db))
    finally:
        db.close()


@app.get("/api/overview/out_of_stock")
async def overview_out_of_stock():
    """在庫切れ出品リスト（ダッシュボードOOSカード用）"""
    from database.crud import get_out_of_stock_items

    db = get_db()
    try:
        return JSONResponse(get_out_of_stock_items(db, limit=10))
    finally:
        db.close()


@app.get("/api/overview/category_profit")
async def overview_category_profit():
    """カテゴリ別利益内訳（モーダル用）"""
    from database.crud import get_category_profit

    db = get_db()
    try:
        today = datetime.now()
        return JSONResponse(get_category_profit(db, today.year, today.month))
    finally:
        db.close()


@app.get("/api/fx/usdjpy")
async def fx_usdjpy():
    """USD/JPY レート（現在は静的値、後でリアルAPI連携予定）"""
    return JSONResponse(
        {
            "rate": 152.40,
            "change": 0.82,
            "direction": "up",
            "source": "static",
            "updated_at": datetime.now().isoformat(),
        }
    )


@app.get("/api/overview/recent_sales")
async def overview_recent_sales():
    """最近の売上明細（ダッシュボード売上テーブル用）"""
    from database.crud import get_recent_sales

    db = get_db()
    try:
        today = datetime.now()
        return JSONResponse(get_recent_sales(db, today.year, today.month, limit=15))
    finally:
        db.close()


# ── エントリーポイント ────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=APP_HOST,
        port=APP_PORT,
        reload=True,
    )
