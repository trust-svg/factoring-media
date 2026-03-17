"""eBay Agent Hub — FastAPI メインサーバー

統合ダッシュボード + REST API + AIエージェントエンドポイント
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import APP_HOST, APP_PORT, DEAL_WATCHER_DB, EBAY_FEE_RATE, PAYONEER_FEE_RATE, PRICE_CHECK_INTERVAL_HOURS, STATIC_DIR, TEMPLATES_DIR
from database.models import get_db, init_db, InventoryItem, Listing
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

# グローバル例外ハンドラー（デバッグ用）
import traceback as _tb
@app.exception_handler(Exception)
async def _global_exc_handler(request: Request, exc: Exception):
    logger.error(f"★ UNHANDLED {request.method} {request.url.path}: {exc}\n{''.join(_tb.format_exception(type(exc), exc, exc.__traceback__))}")
    return JSONResponse(status_code=500, content={"detail": str(exc)})

# 静的ファイル + テンプレート
STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 静的ファイルのキャッシュ無効化（開発用） — raw ASGI middleware（BaseHTTPMiddleware不使用）
from starlette.types import ASGIApp, Receive, Scope, Send

class NoCacheStaticMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http" and scope["path"].startswith("/static/"):
            async def send_with_no_cache(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"cache-control", b"no-cache, no-store, must-revalidate"))
                    message["headers"] = headers
                await send(message)
            await self.app(scope, receive, send_with_no_cache)
        else:
            await self.app(scope, receive, send)

app.add_middleware(NoCacheStaticMiddleware)
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


@app.get("/analytics")
async def analytics_redirect():
    """売上分析は利益管理に統合 — リダイレクト"""
    return RedirectResponse(url="/profit", status_code=301)


@app.get("/messages")
async def messages_redirect():
    """メッセージは一時無効化 — リダイレクト"""
    return RedirectResponse(url="/", status_code=302)


@app.get("/agent", response_class=HTMLResponse)
async def agent_page(request: Request):
    return templates.TemplateResponse("pages/agent.html", {"request": request})


@app.get("/instagram", response_class=HTMLResponse)
async def instagram_page(request: Request):
    return templates.TemplateResponse("pages/instagram.html", {"request": request})


# ── Deal Watcher ──────────────────────────────────────────

def _get_deal_watcher_data():
    """Read deal-watcher DB and return grouped listings with eBay enrichment."""
    import os
    import sqlite3

    dw_db = DEAL_WATCHER_DB
    if not os.path.exists(dw_db):
        return {"groups": [], "keywords": [], "kw_count": 0, "listing_count": 0, "hidden_count": 0}

    conn = sqlite3.connect(dw_db)
    conn.row_factory = sqlite3.Row

    keywords = [dict(r) for r in conn.execute("SELECT * FROM keywords ORDER BY name").fetchall()]
    kw_count = sum(1 for k in keywords if k["active"])
    listing_count = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    hidden_count = conn.execute("SELECT COUNT(*) FROM listings WHERE COALESCE(hidden,0)=1").fetchone()[0]

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
        items = conn.execute("""
            SELECT * FROM listings WHERE keyword_id = ? AND COALESCE(hidden,0) = 0
            ORDER BY price ASC NULLS LAST
        """, (g["id"],)).fetchall()
        groups.append({
            "keyword_id": g["id"], "keyword": g["name"],
            "count": g["listing_count"], "min_price": g["min_price"],
            "max_price": g["max_price"], "latest_found": g["latest_found"],
            "listings": [dict(i) for i in items],
            "ebay_price": None, "ebay_qty": None, "ebay_listing_id": None, "ebay_title": None,
        })
    conn.close()

    # Enrich with eBay data from agent.db + eShip profit data
    db = get_db()
    try:
        ebay_listings = crud.get_all_listings(db)
        ebay_data = {}
        for row in ebay_listings:
            ebay_data[row.sku] = {
                "title": row.title, "title_lower": (row.title or "").lower(),
                "price_usd": row.price_usd, "quantity": row.quantity,
                "listing_id": row.listing_id, "sku": row.sku,
            }

        # Load eShip profit data from file cache (written by /deals/api/eship-sync)
        eship_profits = {}
        try:
            cache_file = os.path.join(os.path.dirname(DEAL_WATCHER_DB), ".eship_profit_cache.json")
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
                eship = eship_profits.get(best["listing_id"], {}) or eship_profits.get(best["sku"], {})
                base_profit = eship.get("profit")       # eShipの登録仕入価格ベースの利益
                eship_pp = eship.get("purchase_price")   # eShipの登録仕入価格

                # Per-listing profit: adjust by price difference
                # adjusted_profit = base_profit + (eship_purchase_price - listing_price)
                for item in group["listings"]:
                    cost_jpy = item.get("price") or 0
                    if base_profit is not None and eship_pp is not None and cost_jpy > 0:
                        adjusted = base_profit + (eship_pp - cost_jpy)
                        item["est_profit_jpy"] = round(adjusted)
                    else:
                        item["est_profit_jpy"] = None

                # Group-level: show best (cheapest listing) profit
                profits = [i["est_profit_jpy"] for i in group["listings"] if i.get("est_profit_jpy") is not None]
                group["eship_profit"] = max(profits) if profits else None
    finally:
        db.close()

    return {
        "groups": groups, "keywords": keywords, "kw_count": kw_count,
        "listing_count": listing_count, "hidden_count": hidden_count,
    }


@app.get("/deals", response_class=HTMLResponse)
async def deals_page(request: Request):
    import httpx
    data = _get_deal_watcher_data()
    scan_status = {"last_run": None, "running": False}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://127.0.0.1:8001/api/status", timeout=3)
            scan_status = resp.json()
    except Exception:
        pass
    return templates.TemplateResponse("pages/deals.html", {
        "request": request, **data,
        "scan_status": scan_status, "interval": 3,
    })


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
    listing = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
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
        row = aconn.execute("SELECT sku FROM listings WHERE title = ?", (ebay_title,)).fetchone()
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
                "UPDATE listings SET quantity = 1 WHERE title = ?",
                (ebay_title,)
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
    """仕入れ実績一覧（売上紐付け情報付き）"""
    db = get_db()
    try:
        procs = crud.get_all_procurements(db, status=status)

        # SKU→売上情報マップ
        sales_by_sku = {}
        all_sales = db.query(crud.SalesRecord).all()
        for s in all_sales:
            if s.sku not in sales_by_sku:
                sales_by_sku[s.sku] = {
                    "sold": True,
                    "sale_price_usd": s.sale_price_usd,
                    "net_profit_jpy": s.net_profit_jpy,
                    "sold_at": s.sold_at.isoformat() if s.sold_at else None,
                    "buyer_name": s.buyer_name,
                }

        result = []
        for p in procs:
            item = {
                "id": p.id,
                "sku": p.sku,
                "platform": p.platform,
                "title": p.title,
                "url": p.url or "",
                "purchase_price_jpy": p.purchase_price_jpy,
                "shipping_cost_jpy": p.shipping_cost_jpy,
                "other_cost_jpy": p.other_cost_jpy,
                "consumption_tax_jpy": p.consumption_tax_jpy,
                "total_cost_jpy": p.total_cost_jpy,
                "status": p.status,
                "purchase_date": p.purchase_date.isoformat() if p.purchase_date else None,
                "received_date": p.received_date.isoformat() if p.received_date else None,
                "notes": p.notes or "",
                "sale": sales_by_sku.get(p.sku),
            }
            result.append(item)
        return result
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
            **({"purchase_date": purchase_date} if purchase_date else {}),
        )
        return JSONResponse({"id": proc.id, "total_cost_jpy": proc.total_cost_jpy, "status": proc.status})
    finally:
        db.close()


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
    kwargs = {}
    for key in ["sku", "platform", "title", "url", "status", "notes"]:
        if key in body:
            kwargs[key] = body[key]
    for key in ["purchase_price_jpy", "shipping_cost_jpy", "other_cost_jpy", "consumption_tax_jpy"]:
        if key in body:
            kwargs[key] = int(body[key])
    if body.get("purchase_date"):
        try:
            kwargs["purchase_date"] = datetime.strptime(body["purchase_date"], "%Y-%m-%d")
        except ValueError:
            pass
    if body.get("received_date"):
        try:
            kwargs["received_date"] = datetime.strptime(body["received_date"], "%Y-%m-%d")
        except ValueError:
            pass
    db = get_db()
    try:
        proc = crud.update_procurement(db, proc_id, **kwargs)
        if not proc:
            raise HTTPException(404, "Procurement not found")
        return JSONResponse({"id": proc.id, "status": proc.status, "total_cost_jpy": proc.total_cost_jpy})
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


# ── 利益管理 ─────────────────────────────────────────────

@app.get("/profit", response_class=HTMLResponse)
async def profit_page(request: Request):
    return templates.TemplateResponse("pages/profit.html", {"request": request})


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
            from_date = (datetime.utcnow() - relativedelta(months=period_months[month])).strftime("%Y-%m-%d")
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
                td = datetime.strptime(to_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                records = [r for r in records if r.sold_at and r.sold_at <= td]
            except ValueError:
                pass

        # SKU→画像URLマップ（一括取得）
        skus = list({r.sku for r in records if r.sku})
        image_map = {}
        if skus:
            listings = db.query(Listing.sku, Listing.image_urls_json).filter(Listing.sku.in_(skus)).all()
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
            procs = db.query(Procurement).filter(Procurement.sku.in_(skus)).order_by(Procurement.created_at.desc()).all()
            for p in procs:
                if p.sku not in proc_map:
                    proc_map[p.sku] = p

        result = []
        for r in records:
            rate = r.exchange_rate or 1.0
            sale_jpy = round(r.sale_price_usd * rate)
            fees_jpy = round((r.ebay_fees_usd + r.payoneer_fee_usd) * rate)

            p = proc_map.get(r.sku)
            proc_info = None
            if p:
                proc_info = {
                    "id": p.id,
                    "purchase_date": p.purchase_date.strftime("%Y-%m-%d") if p.purchase_date else "",
                    "purchase_price_jpy": p.purchase_price_jpy,
                    "consumption_tax_jpy": p.consumption_tax_jpy,
                    "shipping_cost_jpy": p.shipping_cost_jpy,
                    "total_cost_jpy": p.total_cost_jpy,
                    "platform": p.platform,
                    "url": p.url,
                    "status": p.status,
                }

            result.append({
                "id": r.id, "order_id": r.order_id, "item_id": getattr(r, 'item_id', ''),
                "sku": r.sku, "title": r.title,
                "image_url": image_map.get(r.sku, ""),
                "buyer_name": getattr(r, 'buyer_name', ''),
                "buyer_country": getattr(r, 'buyer_country', ''),
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
                "customs_duty_jpy": getattr(r, 'customs_duty_jpy', 0) or 0,
                "other_cost_jpy": r.other_cost_jpy,
                "cost_note": r.cost_note or "",
                "tracking_number": r.tracking_number or "",
                "exchange_rate": r.exchange_rate,
                "total_cost_jpy": r.total_cost_jpy,
                "net_profit_usd": r.net_profit_usd,
                "net_profit_jpy": r.net_profit_jpy,
                "profit_margin_pct": r.profit_margin_pct,
                "sold_at": r.sold_at.strftime("%Y-%m-%d") if r.sold_at else "",
                "progress": getattr(r, 'progress', '') or '',
                "marketplace": getattr(r, 'marketplace', '') or '',
                "listing_site": getattr(r, 'listing_site', '') or '',
                "ship_by_date": r.ship_by_date.strftime("%Y-%m-%d") if getattr(r, 'ship_by_date', None) else '',
                "procurement": proc_info,
            })
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
        return JSONResponse({
            "id": record.id, "net_profit_usd": record.net_profit_usd,
            "net_profit_jpy": record.net_profit_jpy, "profit_margin_pct": record.profit_margin_pct,
            "total_cost_jpy": record.total_cost_jpy,
        })
    finally:
        db.close()


@app.get("/api/expenses")
async def get_expenses_api(month: str = ""):
    db = get_db()
    try:
        expenses = crud.get_expenses(db, year_month=month)
        return JSONResponse([
            {
                "id": e.id, "year_month": e.year_month, "category": e.category,
                "description": e.description, "amount_jpy": e.amount_jpy,
                "amount_usd": e.amount_usd, "is_recurring": bool(e.is_recurring),
            }
            for e in expenses
        ])
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
async def export_tax_report_api(type: str = "sales", year: str = "", from_month: str = "", to_month: str = ""):
    """税務エクスポート CSV"""
    import csv
    import io
    from datetime import datetime as dt
    from fastapi.responses import StreamingResponse

    db = get_db()
    try:
        output = io.StringIO()
        # BOM for Excel
        output.write('\ufeff')

        if type == "sales":
            # 売上明細（税理士メイン資料）
            writer = csv.writer(output)
            writer.writerow([
                "日付", "注文ID", "SKU", "商品名", "売上(USD)", "為替レート", "売上(JPY)",
                "仕入原価(JPY)", "消費税(JPY)", "国内送料(JPY)", "国際送料(JPY)",
                "発送方法", "eBay手数料(USD)", "eBay手数料(JPY)",
                "Payoneer手数料(USD)", "Payoneer手数料(JPY)",
                "その他経費(JPY)", "経費メモ", "全コスト(JPY)", "純利益(JPY)", "利益率(%)",
                "Payoneerレート", "実着金額(JPY)", "為替差損益(JPY)",
            ])
            # 期間フィルタ
            records = db.query(crud.SalesRecord).order_by(crud.SalesRecord.sold_at).all()
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
                ttm_net_jpy = round((r.sale_price_usd - r.ebay_fees_usd - r.payoneer_fee_usd) * rate)
                forex_diff = (r.received_jpy - ttm_net_jpy) if r.received_jpy else 0
                writer.writerow([
                    r.sold_at.strftime("%Y-%m-%d") if r.sold_at else "",
                    r.order_id, r.sku, r.title,
                    f"{r.sale_price_usd:.2f}", f"{rate:.2f}", revenue_jpy,
                    r.source_cost_jpy, r.consumption_tax_jpy,
                    r.shipping_cost_jpy, r.intl_shipping_cost_jpy,
                    r.shipping_method,
                    f"{r.ebay_fees_usd:.2f}", ebay_fees_jpy,
                    f"{r.payoneer_fee_usd:.2f}", payoneer_fees_jpy,
                    r.other_cost_jpy, r.cost_note or "",
                    r.total_cost_jpy, r.net_profit_jpy, f"{r.profit_margin_pct:.1f}",
                    f"{r.payoneer_rate:.2f}" if r.payoneer_rate else "",
                    r.received_jpy or "", forex_diff if r.received_jpy else "",
                ])
            filename = f"ebay_sales_{from_month or year or 'all'}_{to_month or ''}.csv"

        elif type == "monthly":
            # 月次集計（確定申告用）
            writer = csv.writer(output)
            writer.writerow([
                "年月", "売上件数", "売上合計(USD)", "売上合計(JPY)",
                "仕入原価(JPY)", "消費税還付対象(JPY)",
                "国内送料(JPY)", "国際送料(JPY)",
                "eBay手数料(USD)", "Payoneer手数料(USD)",
                "その他経費(JPY)", "固定費(JPY)", "経費合計(JPY)",
                "純利益(JPY)",
            ])
            summary = crud.get_profit_summary(db, months=24)
            for m in sorted(summary, key=lambda x: x["year_month"]):
                if year and not m["year_month"].startswith(year):
                    continue
                total_fees_jpy = round(
                    (m["ebay_fees_usd"] + m["payoneer_fees_usd"]) * (m.get("avg_rate", 150))
                ) if m.get("revenue_usd") else 0
                expense_total = (
                    m["source_cost_jpy"] + m["shipping_jpy"] + m["intl_shipping_jpy"]
                    + m["other_cost_jpy"] + m.get("fixed_cost_jpy", 0) + total_fees_jpy
                )
                writer.writerow([
                    m["year_month"], m["sales_count"],
                    f"{m['revenue_usd']:.2f}", m["revenue_jpy"],
                    m["source_cost_jpy"], m["consumption_tax_jpy"],
                    m["shipping_jpy"], m["intl_shipping_jpy"],
                    f"{m['ebay_fees_usd']:.2f}", f"{m['payoneer_fees_usd']:.2f}",
                    m["other_cost_jpy"], m.get("fixed_cost_jpy", 0),
                    expense_total, m["net_profit_jpy"],
                ])
            filename = f"ebay_monthly_{year or 'all'}.csv"

        elif type == "procurement":
            # 仕入明細（消費税還付用）
            writer = csv.writer(output)
            writer.writerow([
                "日付", "仕入先", "商品名", "仕入額(JPY)", "消費税額(JPY)",
                "送料(JPY)", "その他(JPY)", "合計(JPY)", "SKU", "ステータス",
            ])
            procs = db.query(crud.Procurement).order_by(crud.Procurement.purchase_date).all()
            for p in procs:
                purchase_ym = p.purchase_date.strftime("%Y-%m") if p.purchase_date else ""
                if year and not purchase_ym.startswith(year):
                    continue
                writer.writerow([
                    p.purchase_date.strftime("%Y-%m-%d") if p.purchase_date else "",
                    p.platform, p.title, p.purchase_price_jpy,
                    p.consumption_tax_jpy, p.shipping_cost_jpy,
                    p.other_cost_jpy, p.total_cost_jpy, p.sku, p.status,
                ])
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
                    ratio = SequenceMatcher(None, cp_lower, c.title[:60].lower()).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_candidate = c
                if best_ratio >= 0.7 and best_candidate:
                    record = best_candidate

            if not record:
                not_found.append({
                    "tracking": tracking,
                    "carrier": carrier,
                    "product": product_name[:60],
                    "total": total,
                })
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

        return JSONResponse({
            "status": "ok",
            "matched": matched,
            "skipped": skipped,
            "not_found_count": len(not_found),
            "not_found": not_found[:20],  # 最大20件表示
        })
    finally:
        db.close()


@app.post("/api/sales/sync-all")
async def sync_all_sales(request: Request):
    """Fulfillment API で全期間の注文を取得しDBに同期する"""
    from ebay_core.client import get_all_orders
    from ebay_core.exchange_rate import get_usd_to_jpy

    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    from_date = body.get("from_date", "")  # "YYYY-MM-DD"
    to_date = body.get("to_date", "")

    orders = get_all_orders(from_date=from_date, to_date=to_date)
    if not orders:
        return JSONResponse({"status": "ok", "orders_fetched": 0, "new_records": 0, "skipped_existing": 0})

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
                    db.query(crud.SalesRecord)
                    .filter(
                        crud.SalesRecord.order_id == order_id,
                        crud.SalesRecord.item_id == item.get("item_id", ""),
                    )
                    .first()
                ) if order_id else None

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
                            correct_date = datetime.strptime(created_time[:19], "%Y-%m-%dT%H:%M:%S")
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
                        sold_at = datetime.strptime(created_time[:19], "%Y-%m-%dT%H:%M:%S")
                    except ValueError:
                        pass

                # 仕入れ価格を取得
                source_cost, shipping_cost = crud.get_latest_procurement_cost(db, sku)
                source_cost = source_cost or 0
                shipping_cost = shipping_cost or 0

                # eBay手数料（Fulfillment APIから実額、なければ概算）
                ebay_fees = order.get("ebay_fees_usd") or round(sale_price * EBAY_FEE_RATE, 2)
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

    return JSONResponse({
        "status": "ok",
        "orders_fetched": len(orders),
        "new_records": new_count,
        "skipped_existing": skipped,
    })


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
            return JSONResponse({"status": "ok", "message": "All records already up to date", "updated": 0})

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
            oid for (oid,) in db.query(crud.SalesRecord.order_id)
            .filter(crud.SalesRecord.order_id != "").all()
        )

        for order in orders:
            oid = order.get("order_id", "")
            tn = order.get("tracking_number", "")
            carrier = order.get("shipping_carrier", "")
            buyer_name = order.get("buyer_name", "")
            buyer_country = order.get("buyer_country", "")
            created_time = order.get("created_time", "")

            info = {
                "order_id": oid, "tracking": tn, "carrier": carrier,
                "buyer_name": buyer_name, "buyer_country": buyer_country,
                "created_time": created_time,
            }

            if oid:
                order_by_id[oid] = info

            for item in order.get("items", []):
                info_with_item = {**info, "item_id": item.get("item_id", ""), "sku": item.get("sku", "")}
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
            if not getattr(record, 'buyer_name', '') and info.get("buyer_name"):
                record.buyer_name = info["buyer_name"]
                changed = True
            if not getattr(record, 'buyer_country', '') and info.get("buyer_country"):
                record.buyer_country = info["buyer_country"]
                changed = True
            if not getattr(record, 'item_id', '') and info.get("item_id"):
                record.item_id = info["item_id"]
                changed = True

            # sold_atが不正（全て同じ日時）なら修正
            created_time = info.get("created_time", "")
            if created_time:
                try:
                    correct_date = __import__('datetime').datetime.strptime(
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
        return JSONResponse({
            "status": "ok",
            "updated": updated,
            "total_empty": len(empty_records),
            "orders_fetched": len(orders),
        })
    finally:
        db.close()


# ── 有在庫管理 ─────────────────────────────────────────────

@app.get("/stock", response_class=HTMLResponse)
async def stock_page(request: Request):
    return templates.TemplateResponse("pages/stock.html", {"request": request})


@app.get("/api/stock")
async def list_stock(status: str = ""):
    """仕入れ台帳一覧"""
    db = get_db()
    try:
        items = crud.get_all_inventory_items(db, status=status)
        return JSONResponse([{
            "id": i.id,
            "stock_number": getattr(i, "stock_number", "") or "",
            "sku": i.sku,
            "title": i.title,
            "purchase_price_jpy": i.purchase_price_jpy,
            "consumption_tax_jpy": i.consumption_tax_jpy,
            "shipping_cost_jpy": getattr(i, "shipping_cost_jpy", 0) or 0,
            "purchase_date": i.purchase_date.strftime("%Y-%m-%d") if i.purchase_date else "",
            "purchase_source": i.purchase_source,
            "purchase_url": i.purchase_url,
            "seller_id": getattr(i, "seller_id", "") or "",
            "seller_url": getattr(i, "seller_url", "") or "",
            "quantity": i.quantity,
            "location": i.location,
            "condition": i.condition,
            "status": i.status,
            "ebay_item_id": i.ebay_item_id,
            "ebay_order_id": getattr(i, "ebay_order_id", "") or "",
            "ebay_price_usd": i.ebay_price_usd,
            "listed_at": i.listed_at.strftime("%Y-%m-%d") if i.listed_at else "",
            "sold_at": i.sold_at.strftime("%Y-%m-%d") if i.sold_at else "",
            "shipped_at": (i.shipped_at.strftime("%Y-%m-%d") if getattr(i, "shipped_at", None) else ""),
            "sale_record_id": i.sale_record_id,
            "notes": i.notes or "",
            "image_url": i.image_url,
            "screenshot_path": getattr(i, "screenshot_path", "") or "",
            "days_in_stock": (datetime.utcnow() - i.purchase_date).days if i.purchase_date else 0,
            "total_cost_jpy": i.purchase_price_jpy + i.consumption_tax_jpy + (getattr(i, "shipping_cost_jpy", 0) or 0),
            "created_at": i.created_at.isoformat(),
        } for i in items])
    finally:
        db.close()


@app.get("/api/stock/stats")
async def stock_stats():
    """有在庫KPI統計"""
    db = get_db()
    try:
        return JSONResponse(crud.get_inventory_stats(db))
    finally:
        db.close()


@app.post("/api/stock")
async def add_stock(request: Request):
    """仕入れ台帳にアイテムを登録"""
    body = await request.json()
    db = get_db()
    try:
        kwargs = {}
        for key in ["sku", "title", "purchase_source", "purchase_url", "seller_id", "seller_url",
                     "location", "condition", "status", "ebay_item_id", "ebay_order_id", "notes", "image_url"]:
            if key in body:
                kwargs[key] = body[key]
        for key in ["purchase_price_jpy", "consumption_tax_jpy", "shipping_cost_jpy", "quantity"]:
            if key in body:
                kwargs[key] = int(body[key])
        if body.get("ebay_price_usd"):
            kwargs["ebay_price_usd"] = float(body["ebay_price_usd"])
        for date_key in ["purchase_date", "listed_at", "sold_at", "shipped_at"]:
            if body.get(date_key):
                try:
                    kwargs[date_key] = datetime.strptime(body[date_key], "%Y-%m-%d")
                except ValueError:
                    pass

        item = crud.add_inventory_item(db, **kwargs)
        return JSONResponse({"id": item.id, "status": "created"})
    finally:
        db.close()


@app.put("/api/stock/{item_id}")
async def update_stock(item_id: int, request: Request):
    """仕入れ台帳アイテムを更新"""
    body = await request.json()
    db = get_db()
    try:
        kwargs = {}
        for key in ["sku", "title", "purchase_source", "purchase_url", "seller_id", "seller_url",
                     "location", "condition", "status", "ebay_item_id", "ebay_order_id",
                     "notes", "image_url", "screenshot_path"]:
            if key in body:
                kwargs[key] = body[key]
        for key in ["purchase_price_jpy", "consumption_tax_jpy", "shipping_cost_jpy",
                     "quantity", "sale_record_id"]:
            if key in body:
                kwargs[key] = int(body[key]) if body[key] else 0
        if "ebay_price_usd" in body:
            kwargs["ebay_price_usd"] = float(body["ebay_price_usd"]) if body["ebay_price_usd"] else 0
        for date_key in ["purchase_date", "listed_at", "sold_at", "shipped_at"]:
            if body.get(date_key):
                try:
                    kwargs[date_key] = datetime.strptime(body[date_key], "%Y-%m-%d")
                except ValueError:
                    pass

        item = crud.update_inventory_item(db, item_id, **kwargs)
        if not item:
            raise HTTPException(404, "Inventory item not found")
        return JSONResponse({"id": item.id, "status": item.status})
    finally:
        db.close()


@app.delete("/api/stock/{item_id}")
async def delete_stock(item_id: int):
    """仕入れ台帳アイテムを削除"""
    db = get_db()
    try:
        if not crud.delete_inventory_item(db, item_id):
            raise HTTPException(404, "Inventory item not found")
        return JSONResponse({"status": "deleted"})
    finally:
        db.close()


@app.post("/api/stock/auto-sku")
async def auto_assign_sku():
    """在庫商品の型番をeBay出品とマッチしてSKUを自動付与"""
    import re as _re

    def extract_models(title: str) -> list[str]:
        models = []
        # ブランド+型番
        brand_pats = re.findall(
            r'(?:TASCAM|YAMAHA|SONY|DENON|PIONEER|ROLAND|BOSS|KORG|TECHNICS|CASIO|TEAC|ZOOM|AKAI|MICRO|NAKAMICHI|ACCUPHASE|LUXMAN|MARANTZ|SANSUI|ONKYO|JBL|BOSE|SHURE)'
            r'\s+([A-Za-z0-9][\w\-]+)',
            title, re.IGNORECASE,
        )
        for m in brand_pats:
            if len(m) >= 3:
                models.append(m)

        # 英字+ハイフン+英数字 (DP-2500, GT-PRO, MDS-SD1, SE-A5)
        hyphen = _re.findall(r'[A-Za-z]{1,10}[\-][A-Za-z0-9]{1,10}(?:[\-][A-Za-z0-9]+)*', title)
        for m in hyphen:
            if len(m) >= 4 and m not in models:
                models.append(m)

        # 英字+数字 (MT4X, SU7700, 424MKII)
        alnum = _re.findall(r'[A-Za-z]{1,6}\d{2,5}[A-Za-z]*', title)
        for m in alnum:
            if len(m) >= 4 and m not in models:
                models.append(m)

        # 数字+英字 (424MK, 688)
        numalpha = _re.findall(r'\d{3,5}[A-Za-z]{2,}', title)
        for m in numalpha:
            if len(m) >= 4 and m not in models:
                models.append(m)

        # ゴミ除去
        junk = {'JUNK', 'CD-ROM', 'USB-', 'OK', 'ver', 'No'}
        models = [m for m in models if m not in junk and not m.startswith('N1') and not m.startswith('w2')]

        return models

    import re
    db = get_db()
    try:
        items = db.query(InventoryItem).filter(
            (InventoryItem.sku == "") | (InventoryItem.sku == None)
        ).all()
        listings = db.query(Listing).all()

        # eBayタイトルのインデックス
        listing_map = [(l.sku, l.title.lower(), l.listing_id, l.price_usd) for l in listings]

        assigned = 0
        skipped = 0
        results = []

        for inv in items:
            models = extract_models(inv.title)
            if not models:
                skipped += 1
                continue

            best = None
            best_model_len = 0
            for model in models:
                ml = model.lower()
                if len(ml) < 4:
                    continue
                for sku, lt, listing_id, price_usd in listing_map:
                    if ml in lt:
                        # より長い型番マッチを優先
                        if len(ml) > best_model_len:
                            best = (sku, listing_id, price_usd, model)
                            best_model_len = len(ml)
                        break

            if best:
                inv.sku = best[0]
                inv.ebay_item_id = best[1] or ""
                inv.ebay_price_usd = best[2] or 0
                assigned += 1
                results.append({
                    "stock_number": inv.stock_number,
                    "title": inv.title[:50],
                    "matched_model": best[3],
                    "sku": best[0],
                })
            else:
                skipped += 1

        db.commit()
        return JSONResponse({
            "assigned": assigned,
            "skipped": skipped,
            "total": len(items),
            "matches": results[:20],
        })
    finally:
        db.close()


@app.post("/api/stock/bulk-delete")
async def bulk_delete_stock(request: Request):
    """条件に合う仕入れ台帳アイテムを一括削除"""
    body = await request.json()
    title_contains = body.get("title_contains", "")
    if not title_contains or len(title_contains) < 3:
        raise HTTPException(400, "title_contains must be at least 3 characters")

    db = get_db()
    try:
        items = db.query(InventoryItem).filter(
            InventoryItem.title.contains(title_contains)
        ).all()
        count = len(items)
        for item in items:
            db.delete(item)
        db.commit()
        return JSONResponse({"status": "deleted", "count": count})
    finally:
        db.close()


@app.post("/api/stock/bulk-delete-ids")
async def bulk_delete_stock_by_ids(request: Request):
    """IDリストで仕入れ台帳アイテムを一括削除"""
    body = await request.json()
    ids = body.get("ids", [])
    if not ids:
        raise HTTPException(400, "ids must not be empty")

    db = get_db()
    try:
        count = db.query(InventoryItem).filter(
            InventoryItem.id.in_(ids)
        ).delete(synchronize_session="fetch")
        db.commit()
        return JSONResponse({"status": "deleted", "count": count})
    finally:
        db.close()


@app.post("/api/stock/{item_id}/stock-number")
async def update_stock_number(item_id: int, request: Request):
    """在庫管理番号を更新"""
    body = await request.json()
    stock_number = body.get("stock_number", "")
    db = get_db()
    try:
        item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
        if not item:
            raise HTTPException(404, "Item not found")
        item.stock_number = stock_number
        item.updated_at = datetime.utcnow()
        db.commit()
        return JSONResponse({"id": item_id, "stock_number": stock_number})
    finally:
        db.close()


# ── スクリーンショットアップロード ─────────────────────────

@app.post("/api/stock/{item_id}/screenshot")
async def upload_screenshot(item_id: int, request: Request):
    """仕入元スクリーンショットをアップロード（プラットフォーム別フォルダに保存）"""
    import shutil
    from config import SCREENSHOT_DIR

    db = get_db()
    try:
        item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
        if not item:
            raise HTTPException(404, "Item not found")

        form = await request.form()
        file = form.get("file")
        if not file:
            raise HTTPException(400, "No file uploaded")

        # 年/プラットフォーム別フォルダ
        year = str(datetime.now().year)
        platform = item.purchase_source or "other"
        platform_dir = SCREENSHOT_DIR / year / platform.replace("/", "_").replace(" ", "_")
        platform_dir.mkdir(parents=True, exist_ok=True)

        # ファイル名: ID_日付_商品名(短縮).拡張子
        ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "png"
        safe_title = "".join(c for c in (item.title or "item")[:30] if c.isalnum() or c in "-_ ").strip()
        filename = f"{item.id}_{datetime.now().strftime('%Y%m%d')}_{safe_title}.{ext}"
        filepath = platform_dir / filename

        with open(filepath, "wb") as f:
            content = await file.read()
            f.write(content)

        # DB更新
        item.screenshot_path = str(filepath)
        db.commit()

        return JSONResponse({
            "status": "uploaded",
            "path": str(filepath),
            "platform_dir": str(platform_dir),
        })
    finally:
        db.close()


@app.get("/api/stock/screenshot/{item_id}")
async def get_screenshot(item_id: int):
    """スクリーンショット画像を返す"""
    from fastapi.responses import FileResponse

    db = get_db()
    try:
        item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
        if not item or not item.screenshot_path:
            raise HTTPException(404, "Screenshot not found")
        ss = item.screenshot_path
        # /static/... 形式の場合、プロジェクトルートからの相対パスとして解決
        if ss.startswith("/static/"):
            filepath = Path(__file__).parent / ss.lstrip("/")
        elif ss.startswith("static/"):
            filepath = Path(__file__).parent / ss
        else:
            filepath = Path(ss)
        if not filepath.exists():
            raise HTTPException(404, "Screenshot file not found")
        return FileResponse(str(filepath))
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


# ── 仕入れ→台帳連携 ──────────────────────────────────────

@app.post("/api/stock/from-procurement/{proc_id}")
async def stock_from_procurement(proc_id: int):
    """仕入れ記録から台帳にワンクリック登録"""
    from database.models import Procurement, InventoryItem
    db = get_db()
    try:
        proc = db.query(Procurement).filter(Procurement.id == proc_id).first()
        if not proc:
            raise HTTPException(404, "Procurement not found")

        existing = db.query(InventoryItem).filter(
            InventoryItem.title == proc.title,
            InventoryItem.purchase_price_jpy == proc.purchase_price_jpy,
            InventoryItem.purchase_source == proc.platform,
        ).first()
        if existing:
            return JSONResponse({"status": "already_exists", "id": existing.id,
                                 "message": "この仕入れは既に台帳登録済みです"})

        # ステータスは仕入れの状態に合わせる
        status_map = {"purchased": "ordered", "shipped": "ordered", "received": "received", "listed": "listed"}
        mapped_status = status_map.get(proc.status, "ordered")

        item = crud.add_inventory_item(
            db,
            sku=proc.sku or "",
            title=proc.title,
            purchase_price_jpy=proc.purchase_price_jpy,
            consumption_tax_jpy=proc.consumption_tax_jpy,
            purchase_date=proc.purchase_date,
            purchase_source=proc.platform,
            purchase_url=proc.url or "",
            location="自宅" if mapped_status == "received" else "未着",
            status=mapped_status,
            notes=proc.notes or "",
        )
        return JSONResponse({"status": "created", "id": item.id})
    finally:
        db.close()


# ── 一括インポート ────────────────────────────────────────

@app.post("/api/stock/bulk-import")
async def bulk_import_stock(request: Request):
    """購入履歴テキスト/CSVから一括登録。
    rows: [{title, price, date, source, url, condition, ...}, ...]
    """
    body = await request.json()
    rows = body.get("rows", [])
    platform = body.get("platform", "")  # 一括指定

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

            # 重複チェック（タイトル+価格+仕入先）
            price = int(row.get("price", 0) or 0)
            source = row.get("source") or platform or ""
            existing = db.query(InventoryItem).filter(
                InventoryItem.title == title,
                InventoryItem.purchase_price_jpy == price,
                InventoryItem.purchase_source == source,
            ).first()
            if existing:
                skipped += 1
                continue

            kwargs = {
                "title": title,
                "purchase_price_jpy": price,
                "consumption_tax_jpy": int(row.get("tax", 0) or 0),
                "shipping_cost_jpy": int(row.get("shipping", 0) or 0),
                "purchase_source": source,
                "purchase_url": row.get("url", ""),
                "seller_id": row.get("seller", ""),
                "condition": row.get("condition", ""),
                "status": row.get("status", "ordered"),
                "notes": row.get("notes", ""),
                "image_url": row.get("image_url", ""),
            }
            if row.get("date"):
                try:
                    kwargs["purchase_date"] = datetime.strptime(row["date"], "%Y-%m-%d")
                except ValueError:
                    pass

            crud.add_inventory_item(db, **kwargs)
            created += 1

        return JSONResponse({
            "status": "imported",
            "created": created,
            "skipped": skipped,
            "total": len(rows),
        })
    finally:
        db.close()


# ── ヤフオク一括取込（スクレイパー） ─────────────────────────

# スクレイプジョブの状態管理
_scrape_jobs: dict = {}  # job_id -> {status, message, current, total, results, error}

@app.post("/api/stock/scrape/yahoo")
async def start_yahoo_scrape(request: Request):
    """ヤフオク落札一覧のスクレイピングを開始"""
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
                on_progress=on_progress,
                max_pages=max_pages,
                headless=False,  # 初回ログイン用にheadless=False
            )
            job["results"] = results
            job["status"] = "done"
            job["message"] = f"完了: {len(results)}件取得"
        except RuntimeError as e:
            if str(e) == "LOGIN_REQUIRED":
                job["status"] = "login_required"
                job["message"] = "Yahooログインが必要です。headless=Falseで再実行してください。"
            elif str(e) == "LOGIN_TIMEOUT":
                job["status"] = "error"
                job["message"] = "ログインがタイムアウトしました。"
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


@app.post("/api/stock/scrape/mercari")
async def start_mercari_scrape():
    """メルカリ購入履歴のスクレイピングを開始"""
    import uuid

    job_id = str(uuid.uuid4())[:8]
    _scrape_jobs[job_id] = {
        "status": "running",
        "message": "初期化中...",
        "current": 0, "total": 0,
        "results": [], "error": None,
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
                on_progress=on_progress,
                headless=False,
            )
            job["results"] = results
            job["status"] = "done"
            job["message"] = f"完了: {len(results)}件取得"
        except RuntimeError as e:
            if str(e) == "LOGIN_REQUIRED":
                job["status"] = "login_required"
                job["message"] = "メルカリログインが必要です。"
            elif str(e) == "LOGIN_TIMEOUT":
                job["status"] = "error"
                job["message"] = "ログインがタイムアウトしました。"
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


@app.post("/api/stock/scrape/mercari/import/{job_id}")
async def import_mercari_results(job_id: str):
    """メルカリスクレイプ結果を仕入れ台帳に登録"""
    job = _scrape_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "done":
        raise HTTPException(400, f"Job not ready: {job['status']}")

    results = job.get("results", [])
    if not results:
        return JSONResponse({"created": 0, "skipped": 0, "total": 0})

    # 日付昇順でソート
    results = sorted(results, key=lambda r: r.get("date", "") or "9999")

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
            # 重複チェック
            existing = db.query(InventoryItem).filter(
                InventoryItem.title == title,
                InventoryItem.purchase_price_jpy == price,
                InventoryItem.purchase_source == "メルカリ",
            ).first()
            if existing:
                skipped += 1
                continue

            kwargs = {
                "title": title,
                "purchase_price_jpy": price,
                "shipping_cost_jpy": int(row.get("shipping", 0) or 0),
                "purchase_source": "メルカリ",
                "purchase_url": row.get("item_url", "") or row.get("transaction_url", ""),
                "image_url": row.get("image_url", ""),
                "screenshot_path": row.get("screenshot_path", ""),
                "status": "ordered",
            }
            if row.get("date"):
                try:
                    kwargs["purchase_date"] = datetime.strptime(row["date"], "%Y-%m-%d")
                except ValueError:
                    pass

            crud.add_inventory_item(db, **kwargs)
            created += 1

        _scrape_jobs.pop(job_id, None)

        return JSONResponse({
            "status": "imported",
            "created": created,
            "skipped": skipped,
            "total": len(results),
        })
    finally:
        db.close()


@app.post("/api/stock/retake-screenshots")
async def retake_screenshots():
    """既存のスクリーンショットをfull_pageで再撮影"""
    import uuid

    job_id = str(uuid.uuid4())[:8]
    _scrape_jobs[job_id] = {
        "status": "running",
        "message": "スクリーンショット再撮影中...",
        "current": 0, "total": 0, "results": [], "error": None,
    }

    async def run_retake():
        import re
        from playwright.async_api import async_playwright
        from scrapers.yahoo_auctions import _load_cookies, _save_cookies, COOKIE_DIR

        ss_base = Path("/Users/Mac_air/Library/CloudStorage/GoogleDrive-otsuka@trustlink-tk.com/マイドライブ/総務関連/TrustLink/確定申告資料/輸出業/仕入れ履歴スクリーンショット")

        job = _scrape_jobs[job_id]
        db = get_db()
        try:
            items = db.query(InventoryItem).filter(
                InventoryItem.purchase_source == "ヤフオク",
                InventoryItem.purchase_url != "",
            ).all()

            # auction_idを抽出
            targets = []
            for item in items:
                url = item.purchase_url or ""
                m = re.search(r"auction/([a-zA-Z0-9]+)", url)
                if m:
                    targets.append({"id": item.id, "aid": m.group(1), "item": item})

            job["total"] = len(targets)
            job["message"] = f"0/{len(targets)} 撮影中..."

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    locale="ja-JP",
                )
                await _load_cookies(context)
                page = await context.new_page()

                for idx, t in enumerate(targets):
                    aid = t["aid"]
                    # 仕入日から年を取得
                    year = str(t["item"].purchase_date.year) if t["item"].purchase_date else str(datetime.utcnow().year)
                    platform = t["item"].purchase_source or "その他"
                    ss_dir = ss_base / year / platform
                    ss_dir.mkdir(parents=True, exist_ok=True)
                    ss_path = ss_dir / f"{aid}.png"

                    try:
                        await page.goto(
                            f"https://auctions.yahoo.co.jp/jp/auction/{aid}",
                            wait_until="domcontentloaded", timeout=20000,
                        )
                        await asyncio.sleep(2)
                        await page.screenshot(path=str(ss_path), full_page=True)
                        t["item"].screenshot_path = str(ss_path)
                    except Exception as e:
                        logger.warning(f"Retake SS error ({aid}): {e}")

                    job["current"] = idx + 1
                    job["message"] = f"{idx+1}/{len(targets)} 撮影中..."
                    await asyncio.sleep(0.5)

                await _save_cookies(context)
                await browser.close()

            db.commit()
            job["status"] = "done"
            job["message"] = f"完了: {len(targets)}件再撮影"
        except Exception as e:
            job["status"] = "error"
            job["error"] = str(e)
            job["message"] = f"エラー: {e}"
        finally:
            db.close()

    asyncio.create_task(run_retake())
    return JSONResponse({"job_id": job_id, "status": "started"})


@app.get("/api/stock/scrape/status/{job_id}")
async def get_scrape_status(job_id: str):
    """スクレイプジョブの進捗を確認"""
    job = _scrape_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return JSONResponse({
        "status": job["status"],
        "message": job["message"],
        "current": job["current"],
        "total": job["total"],
        "result_count": len(job.get("results", [])),
        "error": job.get("error"),
    })


@app.post("/api/stock/scrape/import/{job_id}")
async def import_scrape_results(job_id: str):
    """スクレイプ結果を仕入れ台帳に登録"""
    job = _scrape_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "done":
        raise HTTPException(400, f"Job not ready: {job['status']}")

    results = job.get("results", [])
    if not results:
        return JSONResponse({"created": 0, "skipped": 0, "total": 0})

    # 日付昇順でソート（古い商品から登録 → 管理番号が若い番号になる）
    results = sorted(results, key=lambda r: r.get("date", "") or "9999")

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
            # 重複チェック
            existing = db.query(InventoryItem).filter(
                InventoryItem.title == title,
                InventoryItem.purchase_price_jpy == price,
                InventoryItem.purchase_source == "ヤフオク",
            ).first()
            if existing:
                skipped += 1
                continue

            kwargs = {
                "title": title,
                "purchase_price_jpy": price,
                "shipping_cost_jpy": int(row.get("shipping", 0) or 0),
                "consumption_tax_jpy": int(row.get("tax", 0) or 0),
                "purchase_source": "ヤフオク",
                "purchase_url": row.get("url", ""),
                "seller_id": row.get("seller", ""),
                "image_url": row.get("image_url", ""),
                "screenshot_path": row.get("screenshot_path", ""),
                "status": "ordered",
            }
            if row.get("date"):
                try:
                    kwargs["purchase_date"] = datetime.strptime(row["date"], "%Y-%m-%d")
                except ValueError:
                    pass

            crud.add_inventory_item(db, **kwargs)
            created += 1

        # ジョブデータをクリーンアップ
        _scrape_jobs.pop(job_id, None)

        return JSONResponse({
            "status": "imported",
            "created": created,
            "skipped": skipped,
            "total": len(results),
        })
    finally:
        db.close()


# ── eBayディスカバリー ──────────────────────────────────────

@app.get("/discover", response_class=HTMLResponse)
async def discover_page(request: Request):
    return templates.TemplateResponse("pages/discover.html", {"request": request})


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
        return JSONResponse({"results": [], "keyword": keyword, "total": 0, "market_total": 0, "message": "検索結果なし"})

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
            title_words = set(re.findall(r'[a-z0-9]+', title_lower))
            is_known = False
            for known in known_titles:
                known_words = set(re.findall(r'[a-z0-9]+', known))
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

            results.append({
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
            })

        # スコア順
        results.sort(key=lambda x: x["score"], reverse=True)

        return JSONResponse({
            "results": results,
            "keyword": keyword,
            "total": len(results),
            "market_total": market_total,
            "demand_level": demand_level,
            "new_items": sum(1 for r in results if not r["is_known"]),
            "exchange_rate": rate,
        })
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

    return JSONResponse({
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
    })


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
            err_msg = resp.json().get("errors", [{}])[0].get("message", f"HTTP {resp.status_code}")
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
        return JSONResponse({"error": f"No listings found for seller '{seller_name}'"}, status_code=404)

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
        stop_words = {"the", "and", "for", "with", "from", "new", "used", "vintage",
                      "rare", "japan", "japanese", "free", "shipping", "tested", "working"}
        words = re.findall(r'[a-zA-Z]{3,}', title.lower())
        for w in words:
            if w not in stop_words:
                keywords[w] += 1

        items_out.append({
            "title": title,
            "price_usd": price,
            "price_jpy": round(price * rate),
            "condition": cond,
            "category": cat_label,
            "category_id": cat_id,
            "image_url": item.get("image", {}).get("imageUrl", ""),
            "item_url": item.get("itemWebUrl", ""),
        })

    prices.sort()
    avg_price = round(sum(prices) / len(prices), 2) if prices else 0
    median_price = round(prices[len(prices) // 2], 2) if prices else 0

    # 価格帯分布
    price_ranges = {"$0-50": 0, "$50-200": 0, "$200-500": 0, "$500-1000": 0, "$1000+": 0}
    for p in prices:
        if p < 50: price_ranges["$0-50"] += 1
        elif p < 200: price_ranges["$50-200"] += 1
        elif p < 500: price_ranges["$200-500"] += 1
        elif p < 1000: price_ranges["$500-1000"] += 1
        else: price_ranges["$1000+"] += 1

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
            gaps.append({
                "category": cat,
                "seller_count": count,
                "seller_pct": pct,
                "my_count": my_count,
            })
    finally:
        db.close()

    return JSONResponse({
        "seller": seller_name,
        "total_listings": total_listings,
        "fetched": len(items_raw),
        "avg_price_usd": avg_price,
        "median_price_usd": median_price,
        "min_price_usd": round(prices[0], 2) if prices else 0,
        "max_price_usd": round(prices[-1], 2) if prices else 0,
        "categories": [{"name": k, "count": v, "pct": round(v / len(items_raw) * 100)} for k, v in categories.most_common(15)],
        "conditions": [{"name": k, "count": v, "pct": round(v / len(items_raw) * 100)} for k, v in conditions.most_common()],
        "price_ranges": price_ranges,
        "top_keywords": [{"word": k, "count": v} for k, v in keywords.most_common(25)],
        "gap_analysis": gaps,
        "items": items_out[:50],  # 上位50件のみUIに返す
        "exchange_rate": rate,
    })


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
    words = re.findall(r'[A-Za-z0-9][\w\-]*[A-Za-z0-9]', title)
    # ストップワード除外
    stop = {"the", "and", "for", "with", "from", "new", "used", "vintage",
            "rare", "japan", "japanese", "free", "shipping", "tested", "working",
            "pre", "owned", "excellent", "good", "condition", "great", "oem",
            "genuine", "authentic", "original", "box"}
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

    return JSONResponse({
        "title": title,
        "search_query": query,
        "sources": sources,
    })


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
