"""eBay Agent Hub — FastAPI メインサーバー

統合ダッシュボード + REST API + AIエージェントエンドポイント
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import APP_HOST, APP_PORT, PRICE_CHECK_INTERVAL_HOURS, STATIC_DIR, TEMPLATES_DIR
from database.models import get_db, init_db
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
        from pricing.monitor import run_price_monitor
        from comms.scheduled_jobs import send_morning_digest, send_weekly_report, auto_sync_sales

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

        # 売上自動同期（毎日8:00 JST）
        scheduler.add_job(
            auto_sync_sales,
            CronTrigger(hour=8, minute=0, timezone="Asia/Tokyo"),
            id="auto_sync_sales",
            name="売上自動同期",
        )

        # Instagram コンテンツ自動生成（毎日10:00 JST）
        from instagram.scheduler import auto_generate_instagram_content, sync_instagram_analytics
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

        scheduler.start()
        logger.info(
            f"スケジューラー起動: 価格モニター {PRICE_CHECK_INTERVAL_HOURS}h間隔 + "
            f"朝ダイジェスト 9:00 + 週間レポート Mon 10:00 + 売上同期 8:00 + "
            f"Instagram生成 10:00 + Instagram分析 23:00"
        )
        return scheduler
    except ImportError:
        logger.warning("APScheduler 未インストール — スケジューラー無効。pip install apscheduler で有効化できます。")
        return None


app = FastAPI(
    title="eBay Agent Hub",
    description="eBay輸出ビジネス統合AIエージェント",
    version="1.0.0",
    lifespan=lifespan,
)

# 静的ファイル + テンプレート
STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ── ページルート ──────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def overview_page(request: Request):
    db = get_db()
    try:
        stats = crud.get_dashboard_stats(db)
        return templates.TemplateResponse("pages/overview.html", {
            "request": request, "stats": stats,
        })
    finally:
        db.close()


@app.get("/inventory", response_class=HTMLResponse)
async def inventory_page(request: Request):
    db = get_db()
    try:
        listings = crud.get_all_listings(db)
        return templates.TemplateResponse("pages/inventory.html", {
            "request": request, "listings": listings,
        })
    finally:
        db.close()


@app.get("/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request):
    return templates.TemplateResponse("pages/pricing.html", {"request": request})


@app.get("/sourcing", response_class=HTMLResponse)
async def sourcing_page(request: Request):
    return templates.TemplateResponse("pages/sourcing.html", {"request": request})


@app.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    return templates.TemplateResponse("pages/analytics.html", {"request": request})


@app.get("/messages", response_class=HTMLResponse)
async def messages_page(request: Request):
    return templates.TemplateResponse("pages/messages.html", {"request": request})


@app.get("/agent", response_class=HTMLResponse)
async def agent_page(request: Request):
    return templates.TemplateResponse("pages/agent.html", {"request": request})


@app.get("/instagram", response_class=HTMLResponse)
async def instagram_page(request: Request):
    return templates.TemplateResponse("pages/instagram.html", {"request": request})


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
                detail="ANTHROPIC_API_KEY が設定されていません。.env ファイルにキーを追加してください。"
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


# ── 在庫管理 API ──────────────────────────────────────────

@app.get("/api/inventory")
async def get_inventory():
    """全出品の在庫状況を取得"""
    result = await handle_tool_call("check_inventory", {"out_of_stock_only": False})
    import json
    return JSONResponse(json.loads(result))


@app.get("/api/inventory/out-of-stock")
async def get_out_of_stock():
    """在庫切れアイテムのみ取得"""
    result = await handle_tool_call("check_inventory", {"out_of_stock_only": True})
    import json
    return JSONResponse(json.loads(result))


# ── 出品管理 API ──────────────────────────────────────────

@app.get("/api/listings")
async def list_listings():
    db = get_db()
    try:
        listings = crud.get_all_listings(db)
        return [{
            "sku": l.sku,
            "title": l.title,
            "price_usd": l.price_usd,
            "quantity": l.quantity,
            "seo_score": l.seo_score,
            "category_name": l.category_name,
        } for l in listings]
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
            db.query(PriceHistory)
            .join(subq, PriceHistory.id == subq.c.max_id)
            .all()
        )

        alerts = []
        for ph in latest:
            if ph.avg_competitor_price_usd > 0:
                diff = (ph.our_price_usd - ph.avg_competitor_price_usd) / ph.avg_competitor_price_usd * 100
                if abs(diff) > 10:
                    listing = crud.get_listing(db, ph.sku)
                    alerts.append({
                        "sku": ph.sku,
                        "title": listing.title if listing else ph.sku,
                        "our_price": ph.our_price_usd,
                        "avg_competitor": ph.avg_competitor_price_usd,
                        "lowest_competitor": ph.lowest_competitor_price_usd,
                        "diff_pct": round(diff, 1),
                        "action": "値下げ検討" if diff > 10 else "値上げ余地あり",
                        "recorded_at": ph.recorded_at.isoformat(),
                    })

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
        return [{
            "recorded_at": h.recorded_at.isoformat(),
            "our_price": h.our_price_usd,
            "avg_competitor": h.avg_competitor_price_usd,
            "lowest_competitor": h.lowest_competitor_price_usd,
            "num_competitors": h.num_competitors,
            "exchange_rate": h.exchange_rate,
        } for h in history]
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
async def sales_analytics_endpoint(days: int = 30):
    """売上分析レポート"""
    result = await handle_tool_call("get_sales_analytics", {"days": days})
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
        sales = db.query(SalesRecord).order_by(desc(SalesRecord.sold_at)).limit(limit).all()
        changes = db.query(ChangeHistory).order_by(desc(ChangeHistory.applied_at)).limit(limit).all()
        activities = []
        for s in sales:
            activities.append({
                "type": "sale",
                "time": s.sold_at.isoformat(),
                "text": f"Sale: {s.title[:40]} ${s.sale_price_usd:.2f}",
            })
        for c in changes:
            activities.append({
                "type": "change",
                "time": c.applied_at.isoformat(),
                "text": f"Changed: {c.sku[:20]} {c.field_changed}",
            })
        activities.sort(key=lambda a: a["time"], reverse=True)
        return activities[:limit]
    finally:
        db.close()


# ── 仕入れ管理 API ──────────────────────────────────────

@app.get("/api/procurements")
async def list_procurements(status: str = ""):
    """仕入れ実績一覧"""
    db = get_db()
    try:
        procs = crud.get_all_procurements(db, status=status)
        return [{
            "id": p.id,
            "sku": p.sku,
            "platform": p.platform,
            "title": p.title,
            "purchase_price_jpy": p.purchase_price_jpy,
            "shipping_cost_jpy": p.shipping_cost_jpy,
            "total_cost_jpy": p.total_cost_jpy,
            "status": p.status,
            "purchase_date": p.purchase_date.isoformat() if p.purchase_date else None,
            "received_date": p.received_date.isoformat() if p.received_date else None,
        } for p in procs]
    finally:
        db.close()


@app.post("/api/procurements")
async def create_procurement(request: Request):
    """仕入れ実績を記録"""
    body = await request.json()
    result = await handle_tool_call("record_procurement", body)
    return JSONResponse(json.loads(result))


@app.get("/api/procurements/{sku}")
async def get_procurements_by_sku(sku: str):
    """SKU別仕入れ実績"""
    db = get_db()
    try:
        procs = crud.get_procurement_by_sku(db, sku)
        return [{
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
            "purchase_date": p.purchase_date.isoformat() if p.purchase_date else None,
            "received_date": p.received_date.isoformat() if p.received_date else None,
            "notes": p.notes,
        } for p in procs]
    finally:
        db.close()


@app.put("/api/procurements/{proc_id}")
async def update_procurement_endpoint(proc_id: int, request: Request):
    """仕入れ実績を更新"""
    body = await request.json()
    body["procurement_id"] = proc_id
    result = await handle_tool_call("update_procurement", body)
    return JSONResponse(json.loads(result))


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
        return [{
            "id": p.id,
            "sku": p.sku,
            "content_type": p.content_type,
            "tone": p.tone,
            "status": p.status,
            "caption_preview": p.caption[:120] + "..." if len(p.caption) > 120 else p.caption,
            "hashtag_count": len(json.loads(p.hashtags_json)) if p.hashtags_json else 0,
            "image_count": len(json.loads(p.image_urls_json)) if p.image_urls_json else 0,
            "impressions": p.impressions,
            "likes": p.likes,
            "saves": p.saves,
            "created_at": p.created_at.isoformat(),
            "published_at": p.published_at.isoformat() if p.published_at else None,
            "scheduled_at": p.scheduled_at.isoformat() if p.scheduled_at else None,
        } for p in posts]
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
            "image_urls": json.loads(post.image_urls_json) if post.image_urls_json else [],
            "slide_suggestions": json.loads(post.slide_suggestions_json) if post.slide_suggestions_json else [],
            "status": post.status,
            "ig_post_id": post.ig_post_id,
            "impressions": post.impressions,
            "reach": post.reach,
            "likes": post.likes,
            "comments": post.comments,
            "saves": post.saves,
            "link_clicks": post.link_clicks,
            "created_at": post.created_at.isoformat(),
            "published_at": post.published_at.isoformat() if post.published_at else None,
            "scheduled_at": post.scheduled_at.isoformat() if post.scheduled_at else None,
        }
    finally:
        db.close()


@app.post("/api/instagram/dm-reply")
async def instagram_dm_reply_endpoint(request: Request):
    """DM返信ドラフト生成"""
    body = await request.json()
    result = await handle_tool_call("generate_dm_reply", body)
    return JSONResponse(json.loads(result))


# ── ヘルスチェック ────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "ebay-agent-hub"}


# ── エントリーポイント ────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=APP_HOST,
        port=APP_PORT,
        reload=True,
    )
