import asyncio
import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
import database as db
from notifier import notify_line
from scrapers import ALL_SCRAPERS
from auto_sourcing import (
    evaluate_listing,
    process_candidate,
    save_non_candidate,
    reset_notify_counts,
)
from discovery import (
    init_demand_tables,
    collect_demand_data,
    collect_from_own_sales,
    run_discovery_scan,
    create_ebay_listing_from_candidate,
    create_ebay_listing_from_rare_candidate,
)
from ebay_oos_sync import sync_own_oos_keywords
from url_to_listing import url_to_listing
from report import generate_scan_report
from rare_scanner import scan_rare_items, ebay_market_research

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
templates = Jinja2Templates(directory="templates")

# Track scan status
scan_status = {"running": False, "last_run": None, "results": {}}


SCAN_TIMEOUT = 25 * 60  # 25 minutes max per scan cycle
KEYWORD_TIMEOUT = 30  # 30 seconds per keyword (all scrapers combined)


async def _scan_one_keyword(kw, new_count_ref):
    """Scan a single keyword across all platforms. Timeout-safe."""
    keyword_name = kw["name"]
    keyword_id = kw["id"]

    # Run all scrapers concurrently for this keyword, with per-keyword timeout
    tasks = [scraper.search(keyword_name) for scraper in ALL_SCRAPERS]
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=KEYWORD_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning(f"Keyword timeout: {keyword_name}")
        return

    for scraper, result in zip(ALL_SCRAPERS, results):
        if isinstance(result, Exception):
            logger.error(f"[{scraper.platform}] {keyword_name}: {result}")
            continue

        # Relevance filter: all keyword words must appear in title
        kw_words = keyword_name.lower().split()
        filtered = [
            item for item in result if all(w in item.title.lower() for w in kw_words)
        ]
        if len(filtered) < len(result):
            logger.info(
                f"[{scraper.platform}] {keyword_name}: "
                f"filtered {len(result) - len(filtered)}/{len(result)} irrelevant"
            )
        scan_status["results"][scraper.platform] = len(filtered)

        for item in filtered:
            is_new = await db.save_listing(
                platform=item.platform,
                external_id=item.external_id,
                title=item.title,
                price=item.price,
                url=item.url,
                image_url=item.image_url,
                keyword_id=keyword_id,
            )
            if is_new:
                new_count_ref[0] += 1

                if config.AUTO_SOURCE_MODE != "off":
                    try:
                        listing_data = {
                            "platform": item.platform,
                            "title": item.title,
                            "price": item.price,
                            "url": item.url,
                            "image_url": item.image_url,
                            "external_id": item.external_id,
                        }
                        candidate, reason = await evaluate_listing(
                            keyword_name,
                            listing_data,
                        )
                        if candidate:
                            await process_candidate(candidate, 0)
                        elif reason not in ("price_zero", "accessory"):
                            await save_non_candidate(listing_data, reason)
                    except Exception as e:
                        logger.error(f"Auto-sourcing error: {e}")
                else:
                    await notify_line(item.platform, item.title, item.price, item.url)


async def run_scan():
    """Run a full scan across all platforms for all active keywords."""
    if scan_status["running"]:
        logger.info("Scan already running, skipping")
        return

    scan_status["running"] = True
    reset_notify_counts()  # Reset per-eBay-item notification limits
    keywords = await db.get_keywords(active_only=True)
    new_count_ref = [0]  # mutable ref for nested func
    import time

    scan_start = time.time()

    try:
        for kw in keywords:
            elapsed = time.time() - scan_start
            if elapsed > SCAN_TIMEOUT:
                logger.warning(f"Scan timeout after {elapsed:.0f}s, stopping")
                break

            try:
                await _scan_one_keyword(kw, new_count_ref)
            except Exception as e:
                logger.error(f"Keyword scan error [{kw['name']}]: {e}")

            await asyncio.sleep(1)

    except Exception as e:
        logger.error(f"Scan error: {e}")
    finally:
        scan_status["running"] = False
        from datetime import datetime

        scan_status["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Scan complete. {new_count_ref[0]} new listings found.")


async def refresh_eship_cache():
    """Refresh eShip profit cache periodically."""
    try:
        from eship import fetch_eship_profits

        profits = await fetch_eship_profits()
        if profits:
            logger.info(f"eShip cache refreshed: {len(profits)} items")
        else:
            logger.warning("eShip returned 0 items, keeping previous cache")
    except Exception as e:
        logger.error(f"eShip cache refresh failed: {e}")


async def retry_failed_eship():
    """Retry eShip registration for discovery candidates that failed."""
    import aiosqlite
    from discovery import create_eship_item_from_candidate

    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db2:
            db2.row_factory = aiosqlite.Row
            cur = await db2.execute(
                "SELECT * FROM discovery_candidates WHERE status='listed' AND eship_registered=0 ORDER BY created_at DESC LIMIT 10"
            )
            rows = await cur.fetchall()

        if not rows:
            return

        logger.info(f"eShip retry: {len(rows)} candidates to retry")
        for row in rows:
            cid = row["id"]
            try:
                ok = await create_eship_item_from_candidate(cid)
                if ok:
                    logger.info(
                        f"eShip retry success: {cid} ({row['brand']} {row['model']})"
                    )
                else:
                    logger.warning(
                        f"eShip retry failed: {cid} ({row['brand']} {row['model']})"
                    )
            except Exception as e:
                logger.error(f"eShip retry error [{cid}]: {e}")
            await asyncio.sleep(5)
    except Exception as e:
        logger.error(f"eShip retry job error: {e}")


# Watchdog state for run_demand_update
_demand_task: Optional[asyncio.Task] = None
_demand_started_at: Optional[datetime] = None
DEMAND_HANG_THRESHOLD_SEC = 7200  # 2 hours


async def run_demand_update():
    """Periodic demand DB update + discovery scan."""
    global _demand_task, _demand_started_at
    _demand_task = asyncio.current_task()
    _demand_started_at = datetime.now()
    try:
        try:
            count = await collect_demand_data(max_queries=30)
            own = await collect_from_own_sales()
            # Collect competitor products (products others sell but we don't)
            from discovery import collect_competitor_products

            comp = await collect_competitor_products(max_pages=10)
            logger.info(
                f"Demand update: {count} eBay items, {own} own sales, {comp} competitor products"
            )
        except Exception as e:
            logger.error(f"Demand update error: {e}")

        try:
            found = await run_discovery_scan(max_items=100)
            logger.info(f"Discovery scan: {found} candidates")

            # Generate HTML report after scan
            report_file = await generate_scan_report()
            if report_file:
                report_url = f"https://dw.trustlink-tk.com/reports/{report_file}"
                from notifier import notify_telegram_text

                await notify_telegram_text(
                    f"📊 <b>スキャンレポート生成</b>\n"
                    f"新規出品候補 + 仕入れ候補をまとめました\n\n"
                    f'<a href="{report_url}">レポートを開く</a>'
                )
        except asyncio.CancelledError:
            logger.warning("Discovery scan cancelled by watchdog")
            raise
        except Exception as e:
            logger.error(f"Discovery scan error: {e}")
    finally:
        _demand_task = None
        _demand_started_at = None


async def sync_ebay_quantities():
    """eBay実在庫をAPIから取得してebay_agent.dbのquantityを更新する。"""
    try:
        from ebay_core.client import get_active_listings
        from auto_sourcing import AGENT_DB
        import sqlite3

        items = await asyncio.get_event_loop().run_in_executor(
            None, get_active_listings
        )
        if not items:
            logger.warning("sync_ebay_quantities: get_active_listings returned 0 items")
            return

        conn = sqlite3.connect(AGENT_DB)
        updated = 0
        for item in items:
            qty = (
                item.quantity
                if hasattr(item, "quantity")
                else (item.get("quantity", 0) if isinstance(item, dict) else 0)
            )
            sku = item.sku if hasattr(item, "sku") else item.get("sku", "")
            if sku:
                conn.execute("UPDATE listings SET quantity=? WHERE sku=?", (qty, sku))
                updated += 1
        conn.commit()
        conn.close()
        logger.info(
            f"sync_ebay_quantities: {updated}件のqty更新完了（全{len(items)}件）"
        )
    except Exception as e:
        logger.error(f"sync_ebay_quantities error: {e}")


async def _watchdog_demand_update():
    """Cancel run_demand_update if stuck >2 hours, then trigger immediate retry."""
    global _demand_task, _demand_started_at
    if _demand_task is None or _demand_started_at is None:
        return
    elapsed = (datetime.now() - _demand_started_at).total_seconds()
    if elapsed <= DEMAND_HANG_THRESHOLD_SEC:
        return
    logger.warning(f"demand_update stuck for {int(elapsed)}s — cancelling and retrying")
    _demand_task.cancel()
    _demand_task = None
    _demand_started_at = None
    scheduler.add_job(
        run_demand_update,
        id="demand_retry",
        next_run_time=datetime.now(),
        max_instances=1,
        replace_existing=True,
    )


def _http_self_watchdog(port: int = 8001, interval_sec: int = 60, max_fails: int = 3):
    """Ping own HTTP server from a daemon thread; os._exit(1) if unresponsive.

    Runs in a separate OS thread so it survives asyncio event loop hangs.
    launchd's KeepAlive=true will restart the process.
    """
    import threading, time, urllib.request, urllib.error

    def _loop():
        fails = 0
        time.sleep(90)  # Grace period during startup
        while True:
            time.sleep(interval_sec)
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/health", timeout=10
                ) as r:
                    if r.status == 200:
                        fails = 0
                        continue
                    logger.warning(f"HTTP self-check: status {r.status}")
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                logger.warning(f"HTTP self-check failed: {e}")
            fails += 1
            logger.warning(f"HTTP self-check fail count: {fails}/{max_fails}")
            if fails >= max_fails:
                logger.error(
                    f"HTTP server unresponsive for {max_fails}×{interval_sec}s — exiting for launchd restart"
                )
                os._exit(1)

    threading.Thread(target=_loop, daemon=True, name="http-watchdog").start()
    logger.info(
        f"HTTP self-watchdog armed (every {interval_sec}s, {max_fails} fails → exit)"
    )


def _start_ssh_tunnel():
    """Start SSH tunnel to VPS for external access."""
    import subprocess, shutil

    autossh = shutil.which("autossh") or "/opt/homebrew/bin/autossh"
    # AUTOSSH_GATETIME=0: don't give up if the first connection fails fast
    # (e.g. VPS port 8002 still held by a dying session) — keep retrying.
    env = {**os.environ, "AUTOSSH_GATETIME": "0"}
    try:
        proc = subprocess.Popen(
            [
                autossh,
                "-M",
                "0",
                "-N",
                "-o",
                "ServerAliveInterval=30",
                "-o",
                "ServerAliveCountMax=3",
                "-o",
                "ExitOnForwardFailure=yes",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                "BatchMode=yes",
                "-R",
                "8002:localhost:8001",
                "-R",
                "172.17.0.1:5759:localhost:5759",
                "root@46.250.252.99",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        logger.info(f"SSH tunnel started (PID: {proc.pid})")
        return proc
    except Exception as e:
        logger.warning(f"SSH tunnel failed to start: {e}")
        return None


_tunnel_proc = None


async def _check_tunnel():
    """Restart SSH tunnel if it has died."""
    global _tunnel_proc
    if _tunnel_proc is None or _tunnel_proc.poll() is not None:
        logger.warning("SSH tunnel is down, restarting...")
        _tunnel_proc = _start_ssh_tunnel()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _tunnel_proc
    _tunnel_proc = _start_ssh_tunnel()
    await db.init_db()
    await init_demand_tables()
    scheduler.add_job(
        run_scan,
        "interval",
        minutes=config.CHECK_INTERVAL_MINUTES,
        id="main_scan",
        max_instances=1,
    )
    scheduler.add_job(
        refresh_eship_cache,
        "interval",
        hours=1,
        id="eship_cache_refresh",
        max_instances=1,
    )
    scheduler.add_job(
        run_demand_update,
        "interval",
        hours=6,
        id="demand_update",
        max_instances=1,
    )
    scheduler.add_job(
        _check_tunnel,
        "interval",
        minutes=2,
        id="tunnel_watchdog",
        max_instances=1,
    )
    scheduler.add_job(
        retry_failed_eship,
        "interval",
        minutes=30,
        id="eship_retry",
        max_instances=1,
    )
    scheduler.add_job(
        sync_own_oos_keywords,
        "interval",
        hours=6,
        id="oos_keyword_sync",
        max_instances=1,
    )
    scheduler.add_job(
        _watchdog_demand_update,
        "interval",
        minutes=15,
        id="demand_watchdog",
        max_instances=1,
    )
    scheduler.add_job(
        scan_rare_items,
        "interval",
        minutes=30,
        id="rare_scan",
        max_instances=1,
    )
    scheduler.add_job(
        ebay_market_research,
        "cron",
        day_of_week="sun",
        hour=9,
        minute=0,
        id="ebay_research_weekly",
        max_instances=1,
    )
    scheduler.add_job(
        sync_ebay_quantities,
        "interval",
        hours=6,
        id="ebay_qty_sync",
        max_instances=1,
    )
    scheduler.start()
    logger.info(f"Scheduler started (interval: {config.CHECK_INTERVAL_MINUTES}min)")
    # HTTP liveness watchdog — exits process (for launchd restart) if unresponsive
    _http_self_watchdog()
    # Run initial tasks
    asyncio.create_task(refresh_eship_cache())
    asyncio.create_task(sync_ebay_quantities())
    asyncio.create_task(run_scan())
    # Delayed competitor analysis (wait for API rate limit reset)
    asyncio.create_task(_delayed_competitor_scan())
    # Delay discovery to avoid overwhelming startup
    asyncio.create_task(_delayed_discovery())
    # OOS keyword sync — run 2 min after startup
    asyncio.create_task(_delayed_oos_sync())
    yield
    scheduler.shutdown()
    if _tunnel_proc:
        _tunnel_proc.terminate()
        logger.info("SSH tunnel stopped")


async def _delayed_discovery():
    """Run discovery scan after a delay to let main scan start first."""
    await asyncio.sleep(300)  # 5 min delay
    await run_demand_update()


async def _delayed_oos_sync():
    """Run OOS keyword sync 2 minutes after startup."""
    await asyncio.sleep(120)
    await sync_own_oos_keywords()


async def _delayed_competitor_scan():
    """Analyze competitor sellers after API rate limit resets (2h delay)."""
    await asyncio.sleep(7200)  # 2 hour delay
    logger.info("Starting delayed competitor scan...")
    try:
        import aiosqlite
        from ebay_core.client import get_access_token
        import requests as sync_requests
        import re

        APP_ID = config.__dict__.get(
            "EBAY_CLIENT_ID", "TrustLin-stockmon-PRD-c9584b772-839bf393"
        )
        target_sellers = ["lamitiestore", "kousuke650"]

        all_keywords = set()
        for seller in target_sellers:
            items = []
            for page in range(1, 6):
                try:
                    params = {
                        "OPERATION-NAME": "findItemsIneBayStores",
                        "SERVICE-VERSION": "1.0.0",
                        "SECURITY-APPNAME": APP_ID,
                        "RESPONSE-DATA-FORMAT": "JSON",
                        "storeName": seller,
                        "paginationInput.entriesPerPage": "100",
                        "paginationInput.pageNumber": str(page),
                        "sortOrder": "PricePlusShippingHighest",
                    }
                    resp = sync_requests.get(
                        "https://svcs.ebay.com/services/search/FindingService/v1",
                        params=params,
                        timeout=90,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        result = data.get("findItemsIneBayStoresResponse", [{}])[0]
                        ack = result.get("ack", [""])[0]
                        if ack != "Success":
                            break
                        search_items = result.get("searchResult", [{}])[0].get(
                            "item", []
                        )
                        items.extend(search_items)
                        if not search_items:
                            break
                    else:
                        break
                    await asyncio.sleep(1)
                except Exception:
                    break

            logger.info(f"Competitor {seller}: {len(items)} items found")
            for item in items:
                title = item.get("title", [""])[0]
                price = float(
                    item.get("sellingStatus", [{}])[0]
                    .get("currentPrice", [{}])[0]
                    .get("__value__", "0")
                )
                words = title.split()[:3]
                kw = " ".join(words)
                kw = re.sub(r"[^\w\s\-/]", "", kw).strip()
                if len(kw) > 5 and price >= 100:
                    all_keywords.add(kw)

        # Add keywords
        if all_keywords:
            async with aiosqlite.connect(config.DATABASE_PATH) as conn:
                existing = set(
                    r[0]
                    for r in await conn.execute_fetchall(
                        "SELECT LOWER(name) FROM keywords WHERE active=1"
                    )
                )
                added = 0
                for kw in all_keywords:
                    if kw.lower() not in existing:
                        await conn.execute(
                            "INSERT INTO keywords (name, active) VALUES (?, 1)", (kw,)
                        )
                        added += 1
                await conn.commit()
            logger.info(
                f"Competitor scan complete: {len(all_keywords)} keywords extracted, {added} new added"
            )
        else:
            logger.info(
                "Competitor scan: no keywords extracted (API may still be rate-limited)"
            )

    except Exception as e:
        logger.error(f"Competitor scan error: {e}")


app = FastAPI(title="Deal Watcher", lifespan=lifespan)

# --- Static reports ---
from fastapi.staticfiles import StaticFiles

os.makedirs("reports", exist_ok=True)
app.mount("/reports", StaticFiles(directory="reports", html=True), name="reports")


@app.get("/health")
async def health():
    """Lightweight liveness check consumed by _http_self_watchdog."""
    return {"ok": True}


# --- Dashboard ---


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    keywords = await db.get_keywords(active_only=False)
    groups = await db.get_grouped_listings()
    kw_count = await db.get_keyword_count()
    listing_count = await db.get_listing_count()

    # Enrich groups with eBay data
    ebay_data = db.get_ebay_info()
    for group in groups:
        ebay_match = db.match_ebay_keyword(group["keyword"], ebay_data)
        if ebay_match:
            group["ebay_price"] = ebay_match["price_usd"]
            group["ebay_qty"] = ebay_match["quantity"]
            group["ebay_listing_id"] = ebay_match["listing_id"]
            group["ebay_title"] = ebay_match["title"]
        else:
            group["ebay_price"] = None
            group["ebay_qty"] = None
            group["ebay_listing_id"] = None
            group["ebay_title"] = None

    hidden_count = await db.get_hidden_count()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "keywords": keywords,
            "groups": groups,
            "kw_count": kw_count,
            "listing_count": listing_count,
            "hidden_count": hidden_count,
            "scan_status": scan_status,
            "interval": config.CHECK_INTERVAL_MINUTES,
        },
    )


@app.post("/keywords/add")
async def add_keyword(name: str = Form(...)):
    name = name.strip()
    if name:
        await db.add_keyword(name)
    return RedirectResponse("/", status_code=303)


@app.post("/keywords/{keyword_id}/toggle")
async def toggle_keyword(keyword_id: int):
    await db.toggle_keyword(keyword_id)
    return RedirectResponse("/", status_code=303)


@app.post("/keywords/{keyword_id}/delete")
async def delete_keyword(keyword_id: int):
    await db.delete_keyword(keyword_id)
    return RedirectResponse("/", status_code=303)


@app.post("/scan")
async def manual_scan():
    """Trigger a manual scan."""
    asyncio.create_task(run_scan())
    return RedirectResponse("/", status_code=303)


@app.post("/listings/{listing_id}/hide")
async def hide_listing(listing_id: int):
    await db.hide_listing(listing_id)
    return RedirectResponse("/", status_code=303)


@app.post("/listings/{listing_id}/unhide")
async def unhide_listing(listing_id: int):
    await db.unhide_listing(listing_id)
    return RedirectResponse("/", status_code=303)


@app.post("/keywords/{keyword_id}/hide-all")
async def hide_keyword_listings(keyword_id: int):
    await db.hide_keyword_listings(keyword_id)
    return RedirectResponse("/", status_code=303)


# --- eShip ---


@app.post("/api/eship/send")
async def send_to_eship(
    listing_id: int = Form(...),
    ebay_title: str = Form(...),
):
    """Send a deal-watcher listing to eShip."""
    import aiosqlite
    from eship import update_eship_item

    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,))
        listing = await cur.fetchone()

    if not listing:
        return JSONResponse({"status": "error", "message": "Listing not found"})

    result = await update_eship_item(
        ebay_title=ebay_title,
        supplier_url=listing["url"],
        purchase_price=listing["price"] or 0,
        platform=listing["platform"],
        set_quantity=1,
    )
    return JSONResponse(result)


# --- eShip one-tap from LINE ---


@app.get("/eship/register/{candidate_id}", response_class=HTMLResponse)
async def eship_register_page(candidate_id: str, request: Request):
    """Show confirmation page for one-tap eShip registration from LINE."""
    import aiosqlite

    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM eship_candidates WHERE id = ?", (candidate_id,)
        )
        candidate = await cur.fetchone()

    if not candidate:
        return HTMLResponse("<h2>候補が見つかりません</h2>", status_code=404)

    c = dict(candidate)
    if c["status"] == "done":
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:20px;text-align:center">
        <h2 style="color:#1DB446">✅ 登録済み</h2>
        <p>{c["ebay_title"][:60]}</p>
        <p>既にeShipに登録されています</p>
        </body></html>""")

    return HTMLResponse(f"""
    <html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head>
    <body style="font-family:sans-serif;padding:20px;text-align:center;max-width:500px;margin:0 auto">
    <h2>仕入れ候補</h2>
    <p style="font-size:14px;color:#666">{c["ebay_title"][:60]}</p>
    <table style="margin:10px auto;text-align:left">
    <tr><td>仕入れ価格</td><td><b>¥{c["source_price"]:,}</b></td></tr>
    <tr><td>eBay価格</td><td>${c["ebay_price_usd"]:,.0f}</td></tr>
    <tr><td>見込み利益</td><td style="color:#1DB446"><b>¥{c["profit_jpy"]:,}</b></td></tr>
    <tr><td>仕入元</td><td>{c["source_platform"]}</td></tr>
    </table>
    <div style="display:flex;flex-direction:column;gap:10px;margin-top:16px">
    <form method="POST" action="/eship/register/{candidate_id}">
    <button type="submit" style="background:#1DB446;color:white;border:none;
    padding:14px 0;font-size:16px;border-radius:8px;cursor:pointer;width:100%">
    eShipに登録する</button>
    </form>
    <form method="POST" action="/eship/update-images/{candidate_id}">
    <button type="submit" style="background:#FF6B35;color:white;border:none;
    padding:14px 0;font-size:16px;border-radius:8px;cursor:pointer;width:100%">
    eBay画像を白背景に更新</button>
    </form>
    </div>
    <p style="margin-top:12px"><a href="{c["source_url"]}" target="_blank" style="color:#666;font-size:13px">商品ページを確認</a></p>
    </body></html>""")


@app.post("/eship/register/{candidate_id}", response_class=HTMLResponse)
async def eship_register_execute(candidate_id: str):
    """Execute eShip registration from one-tap button."""
    import aiosqlite
    from eship import update_eship_item

    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM eship_candidates WHERE id = ?", (candidate_id,)
        )
        candidate = await cur.fetchone()

    if not candidate:
        return HTMLResponse("<h2>候補が見つかりません</h2>", status_code=404)

    c = dict(candidate)
    if c["status"] == "done":
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:20px;text-align:center">
        <h2 style="color:#1DB446">✅ 既に登録済み</h2>
        <p>{c["ebay_title"][:60]}</p>
        </body></html>""")

    # Execute eShip registration
    result = await update_eship_item(
        ebay_title=c["ebay_title"],
        supplier_url=c["source_url"],
        purchase_price=c["source_price"],
        platform=c["source_platform"],
        set_quantity=1,
        sku=c["sku"] or "",
    )

    if result.get("status") == "ok":
        # Mark as done
        async with aiosqlite.connect(config.DATABASE_PATH) as conn:
            await conn.execute(
                "UPDATE eship_candidates SET status = 'done' WHERE id = ?",
                (candidate_id,),
            )
            await conn.commit()

        # Update agent.db quantity
        from auto_sourcing import _update_agent_qty

        _update_agent_qty(c["ebay_title"])

        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:20px;text-align:center">
        <h2 style="color:#1DB446">✅ eShip登録完了！</h2>
        <p>{c["ebay_title"][:60]}</p>
        <p>仕入¥{c["source_price"]:,} → 見込み利益¥{c["profit_jpy"]:,}</p>
        </body></html>""")
    else:
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:20px;text-align:center">
        <h2 style="color:#e74c3c">❌ 登録失敗</h2>
        <p>{result.get("message", "Unknown error")}</p>
        <p><a href="/eship/register/{candidate_id}">再試行</a></p>
        </body></html>""")


@app.post("/eship/update-images/{candidate_id}", response_class=HTMLResponse)
async def eship_update_images(candidate_id: str):
    """仕入れ候補（eship_candidates）のeBay出品画像を白背景化＋eShipの仕入元URL・在庫数も更新する。"""
    import aiosqlite
    from discovery import apply_white_bg_to_ebay_listing
    from eship import update_eship_item

    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM eship_candidates WHERE id = ?", (candidate_id,)
        )
        candidate = await cur.fetchone()

    if not candidate:
        return HTMLResponse("<h2>候補が見つかりません</h2>", status_code=404)

    c = dict(candidate)
    item_id = c.get("listing_id", "")
    if not item_id:
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:20px;text-align:center">
        <h2 style="color:#e74c3c">エラー</h2>
        <p>eBay ItemID が登録されていません</p>
        <p><a href="/eship/register/{candidate_id}">戻る</a></p>
        </body></html>""")

    # 1) 仕入れ元ページをスクレイピングして画像取得 → 白背景化 → eBay差し替え
    result = await apply_white_bg_to_ebay_listing(
        item_id, source_listing_url=c.get("source_url", "")
    )

    if result.get("status") != "ok":
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:20px;text-align:center">
        <h2 style="color:#e74c3c">エラー（画像更新）</h2>
        <p>{result.get("message", "Unknown error")}</p>
        <p><a href="/eship/register/{candidate_id}">戻る</a></p>
        </body></html>""")

    pics = result.get("pics_count", 0)
    ebay_link = f"https://www.ebay.com/itm/{item_id}"

    # 2) eShip側の仕入元URL・在庫数(=1)・購入価格を更新
    eship_result = await update_eship_item(
        ebay_title=c["ebay_title"],
        supplier_url=c["source_url"],
        purchase_price=c["source_price"],
        platform=c["source_platform"],
        set_quantity=1,
        sku=c["sku"] or "",
    )
    eship_ok = eship_result.get("status") == "ok"
    eship_msg = eship_result.get("message", "")

    # 3) DBステータス更新 + ebay_agent.db数量同期
    if eship_ok:
        async with aiosqlite.connect(config.DATABASE_PATH) as conn:
            await conn.execute(
                "UPDATE eship_candidates SET status = 'done' WHERE id = ?",
                (candidate_id,),
            )
            await conn.commit()
        try:
            from auto_sourcing import _update_agent_qty

            _update_agent_qty(c["ebay_title"])
        except Exception as e:
            logger.warning(f"_update_agent_qty failed: {e}")

    eship_html = (
        f'<p style="color:#1DB446">✅ eShip 仕入元URL・在庫1で更新完了</p>'
        if eship_ok
        else f'<p style="color:#e74c3c">⚠️ eShip更新失敗: {eship_msg}</p>'
    )

    return HTMLResponse(f"""
    <html><head>
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <script>window.onload = function() {{ window.open('{ebay_link}', '_blank'); }};</script>
    </head>
    <body style="font-family:sans-serif;padding:20px;text-align:center;max-width:500px;margin:0 auto">
    <h2 style="color:#1DB446">画像更新完了</h2>
    <p style="color:#1DB446">{pics}枚をEPS（白背景）で差し替えました</p>
    {eship_html}
    <p style="font-size:13px;color:#666">{c["ebay_title"][:60]}</p>
    <div style="margin-top:16px;display:flex;gap:10px;justify-content:center">
    <a href="{ebay_link}" target="_blank" style="background:#0064D2;color:white;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:bold">eBay出品を確認</a>
    <a href="/eship/register/{candidate_id}" style="background:#eee;color:#333;padding:12px 20px;border-radius:8px;text-decoration:none">戻る</a>
    </div>
    </body></html>""")


# --- Candidate Reject (learning) ---


@app.get("/candidate/reject/{candidate_id}", response_class=HTMLResponse)
async def candidate_reject_page(candidate_id: str):
    """Show rejection form for a sourcing candidate."""
    import aiosqlite

    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM eship_candidates WHERE id = ?", (candidate_id,)
        )
        candidate = await cur.fetchone()

    if not candidate:
        return HTMLResponse("<h2>候補が見つかりません</h2>", status_code=404)

    c = dict(candidate)
    if c["status"] == "rejected":
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:20px;text-align:center">
        <h2 style="color:#e74c3c">見送り済み</h2>
        <p>{c["ebay_title"][:60]}</p>
        <p>キーワード: <b>{c.get("reject_keywords", "")}</b></p>
        <p>理由: {c.get("reject_note", "")}</p>
        </body></html>""")

    return HTMLResponse(f"""
    <html><body style="font-family:sans-serif;padding:20px;max-width:500px;margin:0 auto">
    <h2 style="color:#e74c3c">見送り理由を入力</h2>
    <p style="font-size:14px;color:#666">{c["ebay_title"][:80]}</p>
    <table style="margin:10px 0;text-align:left;width:100%">
    <tr><td>仕入れ価格</td><td><b>¥{c["source_price"]:,}</b></td></tr>
    <tr><td>eBay価格</td><td>${c["ebay_price_usd"]:,.0f}</td></tr>
    <tr><td>見込み利益</td><td>¥{c["profit_jpy"]:,}</td></tr>
    </table>
    <form method="POST" action="/candidate/reject/{candidate_id}">

    <p style="margin-top:15px;font-weight:bold">除外キーワード</p>
    <p style="font-size:12px;color:#888">この商品を今後除外するためのキーワードをカンマ区切りで入力<br>
    例: ジャンク, 部品取り / 色違い, ブラック / 海外版</p>
    <input type="text" name="keywords" style="width:100%;box-sizing:border-box;padding:10px;
    border:1px solid #ddd;border-radius:6px;font-size:14px"
    placeholder="キーワード1, キーワード2">

    <p style="margin-top:15px;font-weight:bold">見送り理由（任意）</p>
    <textarea name="note" rows="3" style="width:100%;box-sizing:border-box;padding:10px;
    border:1px solid #ddd;border-radius:6px;font-size:14px"
    placeholder="例: 状態が悪い、この型番は売れにくい、など"></textarea>

    <button type="submit" style="background:#e74c3c;color:white;border:none;
    padding:15px 40px;font-size:16px;border-radius:8px;margin-top:10px;
    cursor:pointer;width:100%">見送りとして記録</button>
    </form>
    <p style="margin-top:10px;text-align:center">
    <a href="{c["source_url"]}" target="_blank">商品ページを確認</a></p>
    </body></html>""")


@app.post("/candidate/reject/{candidate_id}", response_class=HTMLResponse)
async def candidate_reject_submit(
    candidate_id: str,
    keywords: str = Form(""),
    note: str = Form(""),
):
    """Save candidate rejection with learning keywords."""
    import aiosqlite
    from auto_sourcing import _reject_patterns_cache

    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM eship_candidates WHERE id = ?", (candidate_id,)
        )
        candidate = await cur.fetchone()

    if not candidate:
        return HTMLResponse("<h2>候補が見つかりません</h2>", status_code=404)

    keywords_clean = keywords.strip()
    note_clean = note.strip()

    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        await conn.execute(
            """UPDATE eship_candidates
               SET status = 'rejected', reject_note = ?, reject_keywords = ?
               WHERE id = ?""",
            (note_clean, keywords_clean, candidate_id),
        )
        await conn.commit()

    # Invalidate pattern cache so new pattern takes effect immediately
    _reject_patterns_cache["ts"] = 0

    kw_display = keywords_clean if keywords_clean else "なし"
    return HTMLResponse(f"""
    <html><body style="font-family:sans-serif;padding:20px;text-align:center">
    <h2 style="color:#e74c3c">見送りとして記録しました</h2>
    <p>{dict(candidate)["ebay_title"][:60]}</p>
    <p>除外キーワード: <b>{kw_display}</b></p>
    <p style="color:#888">今後、同じキーワードを含む商品は自動的にフィルタされます。</p>
    </body></html>""")


# --- Feedback (learning data) ---


@app.get("/feedback/{feedback_id}", response_class=HTMLResponse)
async def feedback_page(feedback_id: str, request: Request):
    """Show feedback form for a non-candidate listing."""
    import aiosqlite
    from auto_sourcing import REJECT_REASONS

    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM learning_data WHERE id = ?", (feedback_id,)
        )
        item = await cur.fetchone()

    if not item:
        return HTMLResponse("<h2>データが見つかりません</h2>", status_code=404)

    d = dict(item)
    if d["user_action"] == "sourced":
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:20px;text-align:center">
        <h2 style="color:#f39c12">📝 フィードバック済み</h2>
        <p>{d["listing_title"][:60]}</p>
        <p>ご意見ありがとうございます！学習データとして保存されています。</p>
        </body></html>""")

    reason_label = REJECT_REASONS.get(d["rejection_reason"], d["rejection_reason"])
    price = d["listing_price"] or 0

    return HTMLResponse(f"""
    <html><body style="font-family:sans-serif;padding:20px;max-width:500px;margin:0 auto">
    <h2 style="color:#f39c12">📝 仕入れフィードバック</h2>
    <p style="font-size:14px;color:#666">{d["listing_title"][:80]}</p>
    <table style="margin:10px 0;text-align:left;width:100%">
    <tr><td>価格</td><td><b>¥{price:,}</b></td></tr>
    <tr><td>プラットフォーム</td><td>{d["platform"]}</td></tr>
    <tr><td>却下理由</td><td style="color:#e74c3c"><b>{reason_label}</b></td></tr>
    </table>
    <form method="POST" action="/feedback/{feedback_id}">
    <p style="margin-top:15px;font-weight:bold">なぜ仕入れたいですか？</p>
    <textarea name="note" rows="4" style="width:100%;box-sizing:border-box;padding:10px;
    border:1px solid #ddd;border-radius:6px;font-size:14px"
    placeholder="例: この型番はeBayで高く売れる、実は在庫切れ商品と同じもの、など"></textarea>
    <button type="submit" style="background:#f39c12;color:white;border:none;
    padding:15px 40px;font-size:16px;border-radius:8px;margin-top:10px;
    cursor:pointer;width:100%">フィードバックを送信</button>
    </form>
    <p style="margin-top:10px;text-align:center">
    <a href="{d["url"]}" target="_blank">商品ページを確認</a></p>
    </body></html>""")


@app.post("/feedback/{feedback_id}", response_class=HTMLResponse)
async def feedback_submit(feedback_id: str, note: str = Form("")):
    """Save user feedback on a non-candidate listing."""
    import aiosqlite

    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM learning_data WHERE id = ?", (feedback_id,)
        )
        item = await cur.fetchone()

    if not item:
        return HTMLResponse("<h2>データが見つかりません</h2>", status_code=404)

    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        await conn.execute(
            "UPDATE learning_data SET user_action = 'sourced', user_note = ? WHERE id = ?",
            (note.strip(), feedback_id),
        )
        await conn.commit()

    return HTMLResponse(f"""
    <html><body style="font-family:sans-serif;padding:20px;text-align:center">
    <h2 style="color:#f39c12">✅ フィードバック保存完了</h2>
    <p>{dict(item)["listing_title"][:60]}</p>
    <p>学習データとして記録しました。今後の判定に活用します。</p>
    </body></html>""")


# --- Discovery (new product pipeline) ---


@app.get("/discovery/approve/{candidate_id}", response_class=HTMLResponse)
async def discovery_approve_page(candidate_id: str):
    """Show approval page for a discovery candidate."""
    import aiosqlite

    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM discovery_candidates WHERE id = ?", (candidate_id,)
        )
        candidate = await cur.fetchone()

    if not candidate:
        return HTMLResponse("<h2>候補が見つかりません</h2>", status_code=404)

    c = dict(candidate)
    if c["status"] == "listed":
        item_id = c.get("ebay_listing_id", "")
        eship_registered = c.get("eship_registered", 0)
        product_name_listed = (
            f"{c['brand']} {c['model']}".strip() or c["source_title"][:40]
        )
        ebay_link = f"https://www.ebay.com/itm/{item_id}" if item_id else "#"
        eship_status = (
            '<span style="color:#1DB446">登録済</span>'
            if eship_registered
            else '<span style="color:#e74c3c">未登録</span>'
        )
        return HTMLResponse(f"""
        <html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head>
        <body style="font-family:sans-serif;padding:20px;max-width:500px;margin:0 auto;text-align:center">
        <h2 style="color:#0066FF">出品済み</h2>
        <p style="font-weight:bold;font-size:16px">{product_name_listed}</p>
        <table style="margin:10px auto;text-align:left">
        <tr><td>eBay ItemID:&nbsp;</td><td><a href="{ebay_link}" target="_blank">{item_id or "―"}</a></td></tr>
        <tr><td>eShip:&nbsp;</td><td>{eship_status}</td></tr>
        </table>
        <hr style="margin:20px 0;border:none;border-top:1px solid #eee">
        <p style="font-size:13px;color:#666;margin-bottom:12px">
          eBay出品の画像を白背景化して差し替えます。
        </p>
        <form method="POST" action="/discovery/update-images/{candidate_id}">
        <button type="submit" style="background:#FF6B35;color:white;border:none;
          padding:15px 40px;font-size:16px;border-radius:8px;cursor:pointer;width:100%">
          eBay画像を白背景に更新
        </button>
        </form>
        </body></html>""")

    product_name = f"{c['brand']} {c['model']}".strip() or c["source_title"][:40]

    return HTMLResponse(f"""
    <html><body style="font-family:sans-serif;padding:20px;max-width:500px;margin:0 auto">
    <h2 style="color:#0066FF">新規出品確認</h2>
    <p style="font-weight:bold;font-size:16px">{product_name}</p>
    <p style="font-size:13px;color:#666">{c["source_title"][:80]}</p>
    <table style="margin:10px 0;text-align:left;width:100%">
    <tr><td>仕入れ価格</td><td><b>¥{c["source_price"]:,}</b></td></tr>
    <tr><td>eBay相場</td><td>${c["ebay_est_price_usd"]:,.0f}</td></tr>
    <tr><td>見込み利益</td><td style="color:#1DB446"><b>¥{c["est_profit_jpy"]:,}</b></td></tr>
    <tr><td>状態</td><td>{c["source_condition"] or "不明"}</td></tr>
    </table>
    <p style="font-size:13px;color:#888">
    「出品する」を押すと以下が自動実行されます：<br>
    1. AI がタイトル・説明文・Item Specifics を生成<br>
    2. eShip にドラフト登録（出品数1）<br>
    3. eBay にドラフト作成（出品数1）<br>
    ※ 両方確認後に手動で公開
    </p>
    <form method="POST" action="/discovery/approve/{candidate_id}">
    <button type="submit" style="background:#0066FF;color:white;border:none;
    padding:15px 40px;font-size:18px;border-radius:8px;margin-top:10px;
    cursor:pointer;width:100%">出品する（自動）</button>
    </form>
    <p style="margin-top:10px;text-align:center">
    <a href="{c["source_url"]}" target="_blank">仕入元を確認</a></p>
    </body></html>""")


@app.post("/discovery/approve/{candidate_id}", response_class=HTMLResponse)
async def discovery_approve_execute(candidate_id: str):
    """Execute auto-listing pipeline for a discovery candidate."""
    result = await create_ebay_listing_from_candidate(candidate_id)

    if result.get("status") == "ok":
        sku = result.get("sku", "")
        offer_id = result.get("offer_id", "")
        eship_id = result.get("eship_inventory_id", "")
        eship_ok = result.get("eship_registered", False)

        eship_link = (
            f"https://eship-tool.com/inventories/{eship_id}/edit"
            if eship_id
            else "https://eship-tool.com/inventories"
        )
        listing_id = result.get("listing_id", "")
        ebay_link = (
            f"https://www.ebay.com/itm/{listing_id}"
            if listing_id
            else "https://www.ebay.com/sh/lst/active"
        )

        return HTMLResponse(f"""
        <html><head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script>
        // Auto-open eShip and eBay in new tabs
        window.onload = function() {{
            window.open('{eship_link}', '_blank');
            setTimeout(function() {{ window.open('{ebay_link}', '_blank'); }}, 1000);
        }};
        </script>
        </head>
        <body style="font-family:sans-serif;padding:20px;text-align:center;max-width:500px;margin:0 auto">
        <h2 style="color:#1DB446">出品処理完了</h2>
        <p>SKU: <b>{sku}</b></p>
        <p>{result.get("title", "")[:60]}</p>
        <table style="margin:15px auto;text-align:left">
        <tr><td>eShip:</td><td>{'<span style="color:#1DB446">登録済</span>' if eship_ok else '<span style="color:#e74c3c">未登録</span>'}</td></tr>
        <tr><td>eBay:</td><td>{'<span style="color:#1DB446">出品作成済（qty=0）</span>' if listing_id else '<span style="color:#e74c3c">作成失敗</span>'}</td></tr>
        </table>
        <div style="display:flex;gap:10px;justify-content:center;margin-top:20px">
        <a href="{eship_link}" target="_blank" style="background:#FF6B35;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:bold">eShipを確認</a>
        <a href="{ebay_link}" target="_blank" style="background:#0064D2;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:bold">eBay出品を確認</a>
        </div>
        <p style="color:#888;font-size:12px;margin-top:15px">※ 新しいタブでeShipとeBayが自動で開きます</p>
        </body></html>""")
    else:
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:20px;text-align:center">
        <h2 style="color:#e74c3c">エラー</h2>
        <p>{result.get("message", "Unknown error")}</p>
        <p><a href="/discovery/approve/{candidate_id}">再試行</a></p>
        </body></html>""")


@app.post("/discovery/update-images/{candidate_id}", response_class=HTMLResponse)
async def discovery_update_images(candidate_id: str):
    """既存eBay出品の画像を白背景化して差し替える（eShip/eBay登録済み前提）。"""
    from discovery import update_ebay_images_white_bg

    result = await update_ebay_images_white_bg(candidate_id)

    if result.get("status") == "ok":
        item_id = result.get("item_id", "")
        pics = result.get("pics_count", 0)
        ebay_link = (
            f"https://www.ebay.com/itm/{item_id}"
            if item_id
            else "https://www.ebay.com/sh/lst/active"
        )
        return HTMLResponse(f"""
        <html><head>
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <script>window.onload = function() {{ window.open('{ebay_link}', '_blank'); }};</script>
        </head>
        <body style="font-family:sans-serif;padding:20px;text-align:center;max-width:500px;margin:0 auto">
        <h2 style="color:#1DB446">画像更新完了</h2>
        <p><span style="color:#1DB446">{pics}枚をEPS（白背景）で差し替えました</span></p>
        <div style="margin-top:20px">
        <a href="{ebay_link}" target="_blank" style="background:#0064D2;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:bold">eBay出品を確認</a>
        </div>
        </body></html>""")
    else:
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:20px;text-align:center">
        <h2 style="color:#e74c3c">エラー</h2>
        <p>{result.get("message", "Unknown error")}</p>
        <p><a href="/discovery/approve/{candidate_id}">戻る</a></p>
        </body></html>""")


@app.get("/discovery/reject/{candidate_id}", response_class=HTMLResponse)
async def discovery_reject_page(candidate_id: str):
    """Show rejection form for a discovery candidate."""
    import aiosqlite

    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM discovery_candidates WHERE id = ?", (candidate_id,)
        )
        candidate = await cur.fetchone()

    if not candidate:
        return HTMLResponse("<h2>候補が見つかりません</h2>", status_code=404)

    c = dict(candidate)
    product_name = f"{c['brand']} {c['model']}".strip() or c["source_title"][:40]

    return HTMLResponse(f"""
    <html><body style="font-family:sans-serif;padding:20px;max-width:500px;margin:0 auto">
    <h2 style="color:#e74c3c">見送り理由を入力</h2>
    <p style="font-weight:bold">{product_name}</p>
    <p style="font-size:13px;color:#666">{c["source_title"][:80]}</p>
    <form method="POST" action="/discovery/reject/{candidate_id}">
    <p style="margin-top:15px;font-weight:bold">除外キーワード</p>
    <p style="font-size:12px;color:#888">今後同様の商品を除外するキーワード（カンマ区切り）</p>
    <input type="text" name="keywords" style="width:100%;box-sizing:border-box;padding:10px;
    border:1px solid #ddd;border-radius:6px;font-size:14px"
    placeholder="キーワード1, キーワード2">
    <p style="margin-top:15px;font-weight:bold">理由（任意）</p>
    <textarea name="note" rows="3" style="width:100%;box-sizing:border-box;padding:10px;
    border:1px solid #ddd;border-radius:6px;font-size:14px"
    placeholder="例: この機種は需要が低い、状態が悪い、など"></textarea>
    <button type="submit" style="background:#e74c3c;color:white;border:none;
    padding:15px 40px;font-size:16px;border-radius:8px;margin-top:10px;
    cursor:pointer;width:100%">見送りとして記録</button>
    </form>
    </body></html>""")


@app.post("/discovery/reject/{candidate_id}", response_class=HTMLResponse)
async def discovery_reject_submit(
    candidate_id: str,
    keywords: str = Form(""),
    note: str = Form(""),
):
    """Save discovery candidate rejection."""
    import aiosqlite
    from auto_sourcing import _reject_patterns_cache

    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        await conn.execute(
            """UPDATE discovery_candidates
               SET status = 'rejected', reject_note = ?, reject_keywords = ?
               WHERE id = ?""",
            (note.strip(), keywords.strip(), candidate_id),
        )
        await conn.commit()

    # Invalidate reject pattern cache
    _reject_patterns_cache["ts"] = 0

    return HTMLResponse(f"""
    <html><body style="font-family:sans-serif;padding:20px;text-align:center">
    <h2 style="color:#e74c3c">見送りとして記録しました</h2>
    <p>除外キーワード: <b>{keywords.strip() or "なし"}</b></p>
    <p style="color:#888">今後の検索に反映されます。</p>
    </body></html>""")


@app.get("/api/discovery/status")
async def discovery_status():
    """Get discovery system status."""
    import aiosqlite

    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        # Demand items count
        cur = await conn.execute("SELECT COUNT(*) FROM demand_items WHERE active=1")
        demand_count = (await cur.fetchone())[0]
        # Candidates stats
        cur = await conn.execute("""
            SELECT status, COUNT(*) as cnt FROM discovery_candidates
            GROUP BY status
        """)
        status_counts = {row[0]: row[1] for row in await cur.fetchall()}
    return {
        "demand_items": demand_count,
        "candidates": status_counts,
    }


@app.post("/api/discovery/scan")
async def manual_discovery_scan():
    """Trigger manual discovery scan."""
    asyncio.create_task(run_demand_update())
    return {"status": "started"}


# --- URL-to-Listing ---


@app.get("/url-to-listing", response_class=HTMLResponse)
async def url_to_listing_form():
    """Web form for URL-to-Listing."""
    return HTMLResponse(f"""
    <html>
    <head><title>URL-to-Listing</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    </head>
    <body style="font-family:sans-serif;padding:20px;max-width:600px;margin:0 auto">
    <h2>URL → eBay出品</h2>
    <p style="color:#666;font-size:13px">
    仕入元のURLを入力すると、AI が自動で eBay 出品を作成します。<br>
    対応: ヤフオク / メルカリ / Yahoo!フリマ / ラクマ / ハードオフ
    </p>
    <form method="POST" action="/url-to-listing" id="listing-form">
    <p><b>仕入元URL <span style="color:red">*</span></b></p>
    <input type="url" name="url" required style="width:100%;box-sizing:border-box;padding:12px;
    border:1px solid #ddd;border-radius:6px;font-size:14px"
    placeholder="https://auctions.yahoo.co.jp/jp/auction/...">

    <div style="display:flex;gap:15px;margin-top:15px">
    <div style="flex:1">
    <p><b>最低利益額 (¥)</b></p>
    <input type="number" name="min_profit" value="{config.AUTO_SOURCE_MIN_PROFIT}"
    style="width:100%;box-sizing:border-box;padding:10px;border:1px solid #ddd;border-radius:6px">
    </div>
    <div style="flex:1">
    <p><b>最低利益率 (%)</b></p>
    <input type="number" name="min_margin" value="{int(config.MIN_PROFIT_MARGIN * 100)}"
    step="1" min="0" max="100"
    style="width:100%;box-sizing:border-box;padding:10px;border:1px solid #ddd;border-radius:6px">
    </div>
    </div>

    <button type="submit" id="submit-btn" style="background:#0066FF;color:white;border:none;
    padding:15px;font-size:16px;border-radius:8px;margin-top:20px;
    cursor:pointer;width:100%">
    出品する（AI自動生成）
    </button>
    </form>

    <script>
    document.getElementById('listing-form').addEventListener('submit', function() {{
        var btn = document.getElementById('submit-btn');
        btn.disabled = true;
        btn.textContent = 'AI処理中... (30秒〜1分)';
        btn.style.background = '#999';
    }});
    </script>

    <div style="margin-top:30px;padding:15px;background:#f8f9fa;border-radius:8px;font-size:13px">
    <b>処理内容:</b><br>
    1. 仕入元ページから商品情報・画像を取得<br>
    2. Research Agent: eBay需要分析・カテゴリ特定<br>
    3. Quality Agent: コンディション評価<br>
    4. Pricing Agent: 最適価格計算<br>
    5. Listing Agent: タイトル・説明文・Item Specifics生成<br>
    6. eShip登録 + eBayドラフト作成
    </div>
    </body></html>""")


@app.post("/url-to-listing", response_class=HTMLResponse)
async def url_to_listing_execute(
    url: str = Form(...),
    min_profit: int = Form(15000),
    min_margin: int = Form(20),
):
    """Execute URL-to-Listing pipeline."""
    result = await url_to_listing(
        url=url.strip(),
        min_profit_jpy=min_profit,
        min_margin=min_margin / 100.0,
    )

    if result.get("status") == "ok":
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:20px;max-width:600px;margin:0 auto">
        <h2 style="color:#1DB446">出品処理完了</h2>
        <table style="width:100%;border-collapse:collapse;margin:15px 0">
        <tr><td style="padding:8px;border-bottom:1px solid #eee">SKU</td>
            <td style="padding:8px;border-bottom:1px solid #eee"><b>{result["sku"]}</b></td></tr>
        <tr><td style="padding:8px;border-bottom:1px solid #eee">タイトル</td>
            <td style="padding:8px;border-bottom:1px solid #eee">{result["title"][:60]}</td></tr>
        <tr><td style="padding:8px;border-bottom:1px solid #eee">eBay価格</td>
            <td style="padding:8px;border-bottom:1px solid #eee"><b>${result["price_usd"]:,.2f}</b></td></tr>
        <tr><td style="padding:8px;border-bottom:1px solid #eee">見込み利益</td>
            <td style="padding:8px;border-bottom:1px solid #eee;color:#1DB446">
            <b>¥{result["profit_jpy"]:,}</b> ({result["margin"]:.0%})</td></tr>
        <tr><td style="padding:8px;border-bottom:1px solid #eee">コンディション</td>
            <td style="padding:8px;border-bottom:1px solid #eee">{result["condition"]}</td></tr>
        <tr><td style="padding:8px;border-bottom:1px solid #eee">画像数</td>
            <td style="padding:8px;border-bottom:1px solid #eee">{result["image_count"]}</td></tr>
        <tr><td style="padding:8px;border-bottom:1px solid #eee">Item Specifics</td>
            <td style="padding:8px;border-bottom:1px solid #eee">{result["specs_count"]}項目</td></tr>
        <tr><td style="padding:8px;border-bottom:1px solid #eee">eShip</td>
            <td style="padding:8px;border-bottom:1px solid #eee">
            {"登録済" if result["eship_registered"] else "未登録"}</td></tr>
        <tr><td style="padding:8px;border-bottom:1px solid #eee">eBay</td>
            <td style="padding:8px;border-bottom:1px solid #eee">
            {"ドラフト作成済" if result["ebay_created"] else "未作成"}
            {f" (Offer: {result['offer_id']})" if result.get("offer_id") else ""}</td></tr>
        </table>
        <p style="color:#888;font-size:13px">
        eBay Seller Hub でドラフトを確認し、写真を追加・調整して公開してください。</p>
        <a href="/url-to-listing" style="display:inline-block;margin-top:15px;padding:10px 20px;
        background:#0066FF;color:white;text-decoration:none;border-radius:6px">
        別の商品を出品</a>
        </body></html>""")
    else:
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:20px;text-align:center">
        <h2 style="color:#e74c3c">エラー</h2>
        <p>{result.get("message", "Unknown error")}</p>
        <a href="/url-to-listing">戻る</a>
        </body></html>""")


@app.post("/api/url-to-listing")
async def api_url_to_listing(request: Request):
    """JSON API for URL-to-Listing."""
    body = await request.json()
    result = await url_to_listing(
        url=body.get("url", ""),
        min_profit_jpy=body.get("min_profit_jpy", 15000),
        min_margin=body.get("min_margin", 0.20),
    )
    return JSONResponse(result)


@app.get("/api/learning-data")
async def api_learning_data(limit: int = 50):
    """Get recent learning data entries."""
    import aiosqlite

    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM learning_data ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


# --- API ---


@app.get("/api/auto-source/status")
async def auto_source_status():
    return {
        "mode": config.AUTO_SOURCE_MODE,
        "min_profit": config.AUTO_SOURCE_MIN_PROFIT,
        "max_price": config.AUTO_SOURCE_MAX_PRICE,
    }


@app.post("/api/auto-source/sync-profits")
async def sync_eship_profits():
    """Manually trigger eShip profit cache refresh."""
    from eship import fetch_eship_profits

    try:
        profits = await fetch_eship_profits()
        return {"status": "ok", "items": len(profits)}
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/api/boost-sold")
async def api_boost_sold():
    """Boost demand_score for items with sales history."""
    import aiosqlite
    from auto_sourcing import AGENT_DB

    agent = sqlite3.connect(AGENT_DB)
    agent.row_factory = sqlite3.Row
    rows = agent.execute("""
        SELECT l.sku, l.title, l.price_usd, l.listing_id,
               COUNT(s.id) as sold_count,
               SUM(CASE WHEN s.net_profit_jpy > 0 THEN s.net_profit_jpy ELSE 0 END) as total_profit
        FROM listings l
        JOIN sales_records s ON l.sku = s.sku
        WHERE l.quantity = 0 AND s.progress != '返品・返金'
        GROUP BY l.sku
        ORDER BY sold_count DESC
    """).fetchall()
    agent.close()

    boosted = 0
    added_kw = 0
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        for row in rows:
            sold = row["sold_count"]
            profit = row["total_profit"] or 0
            score = 100 + (sold * 50) + int(profit / 10000)

            # Get keyword from product_master
            pm = await conn.execute_fetchall(
                "SELECT brand, model FROM product_master WHERE ebay_sku = ?",
                (row["sku"],),
            )
            kw = f"{pm[0][0]} {pm[0][1]}".strip() if pm else row["title"].split()[:3]
            if isinstance(kw, list):
                kw = " ".join(kw)

            # Add keyword if missing
            existing = await conn.execute_fetchall(
                "SELECT 1 FROM keywords WHERE LOWER(name) = ?", (kw.lower(),)
            )
            if not existing:
                await conn.execute(
                    "INSERT INTO keywords (name, active) VALUES (?, 1)", (kw,)
                )
                added_kw += 1

            # Boost demand_score
            await conn.execute(
                "UPDATE demand_items SET demand_score = MAX(demand_score, ?) WHERE LOWER(search_query) = ?",
                (score, kw.lower()),
            )
            boosted += 1

        await conn.commit()

    return {"boosted": boosted, "added_keywords": added_kw, "total_sold_oos": len(rows)}


@app.post("/api/find-competitors")
async def api_find_competitors():
    """Find competitor sellers and extract keywords we don't have."""
    import aiosqlite
    from ebay_core.client import get_access_token
    import requests as sync_requests

    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
    }

    queries = [
        "synthesizer japan tested",
        "vintage amplifier japan tested",
        "DJ controller japan tested",
        "tape recorder japan tested",
        "drum machine japan tested",
        "mixer japan tested",
        "effect pedal japan tested",
        "turntable japan tested",
        "cassette recorder japan tested",
        "audio interface japan tested",
        "condenser microphone japan",
        "studio monitor japan tested",
    ]

    my_seller = "samurai_shop_japan_s"
    sellers = {}
    all_competitor_items = []

    for q in queries:
        try:
            resp = sync_requests.get(
                "https://api.ebay.com/buy/browse/v1/item_summary/search",
                headers=headers,
                params={
                    "q": q,
                    "limit": 50,
                    "filter": "itemLocationCountry:JP",
                    "fieldgroups": "EXTENDED",
                },
                timeout=15,
            )
            if resp.status_code == 200:
                for item in resp.json().get("itemSummaries", []):
                    seller = item.get("seller", {}).get("username", "")
                    price = float(item.get("price", {}).get("value", 0))
                    title = item.get("title", "")
                    if seller and seller != my_seller:
                        if seller not in sellers:
                            sellers[seller] = {"count": 0, "total_price": 0}
                        sellers[seller]["count"] += 1
                        sellers[seller]["total_price"] += price
                        all_competitor_items.append(
                            {"title": title, "price": price, "seller": seller}
                        )
        except Exception:
            continue

    # Extract brand+model keywords from competitor items
    import re

    new_keywords = set()
    for item in all_competitor_items:
        title = item["title"]
        words = title.split()[:4]
        if len(words) >= 2:
            kw = " ".join(words[:3])
            kw = re.sub(r"[^\w\s\-/]", "", kw).strip()
            if len(kw) > 5:
                new_keywords.add(kw)

    # Add keywords we don't have
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        existing = set(
            r[0]
            for r in await conn.execute_fetchall(
                "SELECT LOWER(name) FROM keywords WHERE active=1"
            )
        )
        added = 0
        for kw in new_keywords:
            if kw.lower() not in existing:
                await conn.execute(
                    "INSERT INTO keywords (name, active) VALUES (?, 1)", (kw,)
                )
                existing.add(kw.lower())
                added += 1
        await conn.commit()
        total = (
            await conn.execute_fetchall("SELECT COUNT(*) FROM keywords WHERE active=1")
        )[0][0]

    top_sellers = sorted(sellers.items(), key=lambda x: -x[1]["count"])[:10]
    return {
        "competitors": [
            {
                "seller": s,
                "items": d["count"],
                "avg_price": round(d["total_price"] / d["count"], 0)
                if d["count"]
                else 0,
            }
            for s, d in top_sellers
        ],
        "competitor_items_found": len(all_competitor_items),
        "keywords_added": added,
        "total_keywords": total,
    }


@app.post("/api/add-keywords")
async def api_add_keywords(request: Request):
    """Add keywords in bulk. POST JSON: {"keywords": ["kw1", "kw2", ...]}"""
    import aiosqlite

    data = await request.json()
    keywords = data.get("keywords", [])
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        existing = set(
            r[0]
            for r in await conn.execute_fetchall(
                "SELECT LOWER(name) FROM keywords WHERE active=1"
            )
        )
        added = 0
        for kw in keywords:
            if kw.lower() not in existing:
                await conn.execute(
                    "INSERT INTO keywords (name, active) VALUES (?, 1)", (kw,)
                )
                existing.add(kw.lower())
                added += 1
        await conn.commit()
        total = (
            await conn.execute_fetchall("SELECT COUNT(*) FROM keywords WHERE active=1")
        )[0][0]
    return {"added": added, "total": total}


# --- Keyword management page ---


@app.get("/keywords", response_class=HTMLResponse)
async def keywords_page(request: Request):
    keywords = await db.get_keywords(active_only=False)
    return templates.TemplateResponse(
        "keywords.html", {"request": request, "keywords": keywords}
    )


@app.post("/api/keywords/add")
async def api_keyword_add(request: Request):
    data = await request.json()
    name = (data.get("name") or "").strip()
    if not name:
        return JSONResponse({"error": "キーワードを入力してください"})
    import aiosqlite

    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        existing = await conn.execute_fetchall(
            "SELECT id FROM keywords WHERE LOWER(name) = LOWER(?)", (name,)
        )
        if existing:
            return JSONResponse({"skipped": True, "name": name})
        cur = await conn.execute(
            "INSERT INTO keywords (name, active) VALUES (?, 1)", (name,)
        )
        await conn.commit()
        return JSONResponse({"id": cur.lastrowid, "name": name})


@app.post("/api/keywords/{keyword_id}/toggle")
async def api_keyword_toggle(keyword_id: int):
    await db.toggle_keyword(keyword_id)
    return JSONResponse({"ok": True})


@app.post("/api/keywords/{keyword_id}/delete")
async def api_keyword_delete(keyword_id: int):
    await db.delete_keyword(keyword_id)
    return JSONResponse({"ok": True})


@app.post("/api/keywords/import")
async def api_keywords_import(request: Request):
    data = await request.json()
    keywords = data.get("keywords", [])
    import aiosqlite

    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        existing = set(
            r[0]
            for r in await conn.execute_fetchall("SELECT LOWER(name) FROM keywords")
        )
        added = 0
        skipped = 0
        for kw in keywords:
            kw = kw.strip()
            if not kw:
                continue
            if kw.lower() in existing:
                skipped += 1
            else:
                await conn.execute(
                    "INSERT INTO keywords (name, active) VALUES (?, 1)", (kw,)
                )
                existing.add(kw.lower())
                added += 1
        await conn.commit()
        total = (await conn.execute_fetchall("SELECT COUNT(*) FROM keywords"))[0][0]
    return JSONResponse({"added": added, "skipped": skipped, "total": total})


@app.post("/api/keywords/bulk-delete")
async def api_keywords_bulk_delete(request: Request):
    data = await request.json()
    ids = [int(i) for i in data.get("ids", []) if str(i).isdigit()]
    if not ids:
        return JSONResponse({"ok": False, "deleted": 0})
    import aiosqlite

    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        placeholders = ",".join("?" * len(ids))
        await conn.execute(f"DELETE FROM keywords WHERE id IN ({placeholders})", ids)
        await conn.commit()
    return JSONResponse({"ok": True, "deleted": len(ids)})


@app.post("/api/keywords/{keyword_id}/rename")
async def api_keyword_rename(keyword_id: int, request: Request):
    data = await request.json()
    name = (data.get("name") or "").strip()
    if not name:
        return JSONResponse({"ok": False, "error": "空のキーワードは保存できません"})
    import aiosqlite

    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conflict = await conn.execute_fetchall(
            "SELECT id FROM keywords WHERE LOWER(name)=LOWER(?) AND id!=?",
            (name, keyword_id),
        )
        if conflict:
            return JSONResponse({"ok": False, "error": "同名のキーワードが存在します"})
        await conn.execute("UPDATE keywords SET name=? WHERE id=?", (name, keyword_id))
        await conn.commit()
    return JSONResponse({"ok": True, "name": name})


@app.post("/api/scan-priority")
async def api_scan_priority():
    """Scan only high-priority keywords (sold items that are OOS)."""
    import aiosqlite
    from auto_sourcing import AGENT_DB

    # Get sold OOS SKUs
    agent = sqlite3.connect(AGENT_DB)
    agent.row_factory = sqlite3.Row
    sold_rows = agent.execute("""
        SELECT DISTINCT l.sku, l.title
        FROM listings l
        JOIN sales_records s ON l.sku = s.sku
        WHERE l.quantity = 0 AND s.progress != '返品・返金'
    """).fetchall()
    agent.close()

    # Get matching keywords
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        all_kw = await conn.execute_fetchall(
            "SELECT id, name FROM keywords WHERE active=1"
        )

    # Match keywords to sold items
    priority_kws = []
    sold_titles = [r["title"].lower() for r in sold_rows]
    for kw in all_kw:
        kw_lower = kw["name"].lower()
        if any(kw_lower in t for t in sold_titles):
            priority_kws.append({"id": kw["id"], "name": kw["name"]})

    # Run scan for priority keywords only
    new_count = [0]
    for kw in priority_kws:
        await _scan_one_keyword(kw, new_count)

    return {
        "status": "completed",
        "priority_keywords": len(priority_kws),
        "new_listings": new_count[0],
    }


@app.get("/api/status")
async def api_status():
    return scan_status


@app.get("/api/listings")
async def api_listings(limit: int = 50):
    listings = await db.get_recent_listings(limit=limit)
    return [dict(row) for row in listings]


@app.get("/listings", response_class=HTMLResponse)
async def listings_dashboard():
    """出品管理ダッシュボード — eBay/eShip登録状況を一覧表示"""
    import aiosqlite

    rows = []
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await conn.execute_fetchall("""
            SELECT id, brand, model, source_title, source_price, source_url,
                   ebay_est_price_usd, est_profit_jpy, status,
                   ebay_listing_id, eship_registered, created_at
            FROM discovery_candidates
            WHERE status IN ('listed', 'error', 'pending')
            ORDER BY created_at DESC
            LIMIT 100
        """)

    table_rows = ""
    for r in rows:
        r = dict(r)
        cid = r["id"]
        brand = r.get("brand", "")
        model = r.get("model", "")
        title = r.get("source_title", "")[:50]
        price = r.get("source_price", 0)
        profit = r.get("est_profit_jpy", 0)
        ebay_id = r.get("ebay_listing_id", "")
        eship = r.get("eship_registered", 0)
        status = r.get("status", "")
        created = r.get("created_at", "")[:16]

        # eBay status
        if ebay_id:
            ebay_html = f'<a href="https://www.ebay.com/itm/{ebay_id}" target="_blank" style="color:#1DB446">✅ {ebay_id}</a>'
        else:
            ebay_html = '<span style="color:#e74c3c">❌ 未登録</span>'

        # eShip status
        if eship:
            eship_html = '<span style="color:#1DB446">✅ 登録済</span>'
        else:
            eship_btn = f'<a href="/eship/register-discovery/{cid}" style="background:#FF6B35;color:white;padding:4px 10px;border-radius:4px;text-decoration:none;font-size:12px">eShip登録</a>'
            eship_html = f"❌ {eship_btn}"

        # Profit color
        pcolor = (
            "#1DB446"
            if profit >= 15000
            else "#f39c12"
            if profit >= 10000
            else "#e74c3c"
        )

        # Status badge
        status_colors = {"listed": "#1DB446", "error": "#e74c3c", "pending": "#3498db"}
        status_labels = {"listed": "出品済", "error": "エラー", "pending": "未処理"}
        scolor = status_colors.get(status, "#888")
        slabel = status_labels.get(status, status)

        table_rows += f"""
        <tr>
            <td style="font-size:12px;color:#888">{created}</td>
            <td><b>{brand} {model}</b><br><span style="font-size:11px;color:#666">{title}</span></td>
            <td>¥{price:,}</td>
            <td style="color:{pcolor};font-weight:bold">¥{profit:,}</td>
            <td>{ebay_html}</td>
            <td>{eship_html}</td>
            <td><span style="background:{scolor};color:white;padding:2px 8px;border-radius:10px;font-size:11px">{slabel}</span></td>
            <td style="white-space:nowrap">
                {'<a href="/discovery/approve/' + cid + '" style="background:#1DB446;color:white;padding:4px 8px;border-radius:4px;text-decoration:none;font-size:11px;margin-right:4px">出品する</a>' if status == "pending" else ""}
                <a href="{r.get("source_url", "")}" target="_blank" style="background:#3498db;color:white;padding:4px 8px;border-radius:4px;text-decoration:none;font-size:11px;margin-right:4px">商品</a>
                {'<a href="/candidate/reject/' + cid + '" style="background:#e74c3c;color:white;padding:4px 8px;border-radius:4px;text-decoration:none;font-size:11px">見送り</a>' if status != "rejected" else ""}
            </td>
        </tr>"""

    return HTMLResponse(f"""
    <html><head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>出品管理 — Deal Watcher</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; margin: 0; padding: 15px; background: #f5f5f5; }}
        h1 {{ font-size: 20px; margin: 0 0 15px; }}
        table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        th {{ background: #2c3e50; color: white; padding: 10px 8px; text-align: left; font-size: 12px; }}
        td {{ padding: 8px; border-bottom: 1px solid #eee; font-size: 13px; }}
        tr:hover {{ background: #f8f9fa; }}
        a {{ color: #0066FF; text-decoration: none; }}
        .stats {{ display: flex; gap: 10px; margin-bottom: 15px; }}
        .stat {{ background: white; padding: 12px 16px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .stat b {{ font-size: 20px; }}
    </style>
    </head>
    <body>
    <h1>📦 出品管理ダッシュボード</h1>
    <div class="stats">
        <div class="stat">合計 <b>{len(rows)}</b>件</div>
        <div class="stat">eBay ✅ <b>{sum(1 for r in rows if dict(r).get("ebay_listing_id"))}</b></div>
        <div class="stat">eShip ✅ <b>{sum(1 for r in rows if dict(r).get("eship_registered"))}</b></div>
        <div class="stat">未処理 <b>{sum(1 for r in rows if dict(r).get("status") == "pending")}</b></div>
    </div>
    <table>
    <tr>
        <th>日時</th><th>商品</th><th>仕入</th><th>利益</th><th>eBay</th><th>eShip</th><th>状態</th><th>操作</th>
    </tr>
    {table_rows}
    </table>
    </body></html>""")


@app.get("/eship/register-discovery/{candidate_id}")
async def eship_register_discovery(candidate_id: str):
    """eShipのみ手動登録（eBay出品済みの候補用）"""
    import aiosqlite

    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM discovery_candidates WHERE id = ?", (candidate_id,)
        )
        c = await cur.fetchone()
    if not c:
        return HTMLResponse("<h2>候補が見つかりません</h2>", status_code=404)
    c = dict(c)

    from eship import create_eship_item

    ebay_id = c.get("ebay_listing_id", "") or str(int(time.time()))
    result = await create_eship_item(
        title=f"{c.get('brand', '')} {c.get('model', '')}".strip()
        or c.get("source_title", "")[:50],
        supplier_url=c.get("source_url", ""),
        purchase_price=c.get("source_price", 0),
        platform=c.get("source_platform", ""),
        selling_price_usd=c.get("ebay_est_price_usd", 0),
        sku=c.get("id", "")[:20],
        ebay_item_id=ebay_id,
        condition="Used",
    )

    if result.get("status") == "ok":
        async with aiosqlite.connect(config.DATABASE_PATH) as conn:
            await conn.execute(
                "UPDATE discovery_candidates SET eship_registered = 1 WHERE id = ?",
                (candidate_id,),
            )
            await conn.commit()
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;text-align:center;padding:40px">
        <h2 style="color:#1DB446">✅ eShip登録完了</h2>
        <p>{c.get("brand", "")} {c.get("model", "")}</p>
        <a href="/listings">← 出品管理に戻る</a>
        </body></html>""")
    else:
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;text-align:center;padding:40px">
        <h2 style="color:#e74c3c">❌ eShip登録失敗</h2>
        <p>{result.get("message", "")}</p>
        <a href="/listings">← 出品管理に戻る</a>
        </body></html>""")


# ── Rare item routes ──────────────────────────────────────


@app.get("/rare/keywords", response_class=HTMLResponse)
async def rare_keywords_page():
    keywords = await db.get_rare_keywords(active_only=False)
    rows = ""
    for kw in keywords:
        k = dict(kw)
        active = k["active"] == 1
        badge = (
            '<span style="background:#dcfce7;color:#166534;padding:2px 8px;border-radius:12px;font-size:11px">有効</span>'
            if active
            else '<span style="background:#f3f4f6;color:#6b7280;padding:2px 8px;border-radius:12px;font-size:11px">停止</span>'
        )
        toggle_label = "停止" if active else "再開"
        toggle_color = "#6b7280" if active else "#059669"
        ya_url = f"https://auctions.yahoo.co.jp/search/search?p={kw['name'].replace(' ', '+')}&s1=new&o1=d"
        rows += f"""
        <tr style="border-bottom:1px solid #f3f4f6">
          <td style="padding:12px 8px;font-weight:500">{kw["name"]}</td>
          <td style="padding:12px 8px">{badge}</td>
          <td style="padding:12px 8px;color:#9ca3af;font-size:12px">{kw["created_at"][:10]}</td>
          <td style="padding:12px 8px;display:flex;gap:6px;align-items:center">
            <a href="{ya_url}" target="_blank"
               style="background:#fff7ed;color:#c2410c;border:1px solid #fed7aa;padding:4px 10px;
               border-radius:6px;font-size:12px;text-decoration:none">YA確認</a>
            <form method="POST" action="/rare/keywords/{k["id"]}/toggle" style="display:inline">
              <button type="submit" style="background:#f9fafb;color:{toggle_color};border:1px solid #e5e7eb;
              padding:4px 10px;border-radius:6px;font-size:12px;cursor:pointer">{toggle_label}</button>
            </form>
            <form method="POST" action="/rare/keywords/{k["id"]}/delete"
              onsubmit="return confirm('削除しますか？')" style="display:inline">
              <button type="submit" style="background:#fef2f2;color:#dc2626;border:1px solid #fecaca;
              padding:4px 10px;border-radius:6px;font-size:12px;cursor:pointer">削除</button>
            </form>
          </td>
        </tr>"""

    empty = (
        "<tr><td colspan='4' style='padding:24px;text-align:center;color:#9ca3af'>キーワードがまだありません</td></tr>"
        if not keywords
        else ""
    )
    kw_count = len(list(keywords))

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>レアアイテム監視キーワード</title>
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans",sans-serif;
    background:#f5f7fa;color:#1a1a2e;line-height:1.5}}
  .wrap{{max-width:720px;margin:0 auto;padding:24px 16px}}
  h1{{font-size:20px;font-weight:700;margin-bottom:4px}}
  .sub{{color:#6b7280;font-size:13px;margin-bottom:24px}}
  .card{{background:#fff;border:1px solid #e8ecf1;border-radius:12px;
    padding:20px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
  .card h2{{font-size:14px;font-weight:600;color:#374151;margin-bottom:14px}}
  input[type=text]{{width:100%;padding:10px 12px;border:1px solid #d1d5db;
    border-radius:8px;font-size:14px;outline:none}}
  input[type=text]:focus{{border-color:#4f46e5;box-shadow:0 0 0 3px rgba(79,70,229,.1)}}
  .add-row{{display:flex;gap:8px;margin-top:8px}}
  .btn{{padding:10px 20px;border:none;border-radius:8px;font-size:14px;
    font-weight:500;cursor:pointer;transition:all .15s}}
  .btn-primary{{background:#4f46e5;color:#fff}}
  .btn-primary:hover{{background:#4338ca}}
  .btn-research{{background:#0f766e;color:#fff;font-size:13px;padding:8px 14px}}
  table{{width:100%;border-collapse:collapse}}
  .hint{{font-size:12px;color:#9ca3af;margin-top:6px}}
  .top-row{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:24px}}
</style></head>
<body><div class="wrap">
  <div class="top-row">
    <div>
      <h1>🔍 レアアイテム 監視キーワード</h1>
      <p class="sub">ヤフオク・メルカリを30分ごとに検索します</p>
    </div>
    <form method="POST" action="/rare/ebay-research">
      <button type="submit" class="btn btn-research">📊 eBay調査を今すぐ実行</button>
    </form>
  </div>
  <div class="card">
    <h2>キーワードを追加</h2>
    <form method="POST" action="/rare/keywords/add">
      <input type="text" name="name" placeholder="例: イチロー 直筆サイン" required autocomplete="off">
      <p class="hint">スペース区切りで複数語を含められます。登録後すぐ次のスキャンから有効になります。</p>
      <div class="add-row">
        <button type="submit" class="btn btn-primary">追加</button>
      </div>
    </form>
  </div>
  <div class="card">
    <h2>監視中のキーワード ({kw_count}件)</h2>
    <table>
      <thead>
        <tr style="border-bottom:2px solid #f3f4f6;font-size:12px;color:#6b7280">
          <th style="padding:8px;text-align:left">キーワード</th>
          <th style="padding:8px;text-align:left">状態</th>
          <th style="padding:8px;text-align:left">登録日</th>
          <th style="padding:8px;text-align:left">操作</th>
        </tr>
      </thead>
      <tbody>{rows}{empty}</tbody>
    </table>
  </div>
  <p style="text-align:center;font-size:12px;color:#9ca3af">
    <a href="/" style="color:#4f46e5">← ダッシュボードに戻る</a>
  </p>
</div></body></html>""")


@app.post("/rare/keywords/add")
async def rare_keyword_add(name: str = Form(...)):
    await db.add_rare_keyword(name)
    return RedirectResponse("/rare/keywords", status_code=303)


@app.post("/rare/keywords/{kid}/toggle")
async def rare_keyword_toggle(kid: int):
    await db.toggle_rare_keyword(kid)
    return RedirectResponse("/rare/keywords", status_code=303)


@app.post("/rare/keywords/{kid}/delete")
async def rare_keyword_delete(kid: int):
    await db.delete_rare_keyword(kid)
    return RedirectResponse("/rare/keywords", status_code=303)


@app.post("/rare/ebay-research")
async def trigger_ebay_research():
    asyncio.create_task(ebay_market_research())
    return RedirectResponse("/rare/keywords", status_code=303)


@app.get("/rare/list/{cid}", response_class=HTMLResponse)
async def rare_list_page(cid: str):
    c = await db.get_rare_candidate(cid)
    if not c:
        return HTMLResponse("<h2>候補が見つかりません</h2>", status_code=404)

    if c["status"] == "listed":
        item_id = c.get("ebay_listing_id", "")
        ebay_link = (
            f"https://www.ebay.com/itm/{item_id}"
            if item_id
            else "https://www.ebay.com/sh/lst/active"
        )
        return HTMLResponse(f"""
        <html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head>
        <body style="font-family:sans-serif;padding:20px;text-align:center;max-width:500px;margin:0 auto">
        <h2 style="color:#0066FF">出品済み</h2>
        <p style="font-size:14px;color:#666">{c["title"][:60]}</p>
        <p><a href="{ebay_link}" target="_blank">eBay出品を確認</a></p>
        </body></html>""")

    price_str = f"¥{c['price_jpy']:,}" if c["price_jpy"] else "価格不明"
    from notifier import PLATFORM_LABELS

    platform_label = PLATFORM_LABELS.get(c["platform"], c["platform"])

    return HTMLResponse(f"""
    <html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head>
    <body style="font-family:sans-serif;padding:20px;max-width:500px;margin:0 auto">
    <h2 style="color:#0066FF">新規出品確認</h2>
    <p style="font-weight:bold;font-size:16px">{c["title"][:60]}</p>
    <table style="margin:10px 0;text-align:left;width:100%">
    <tr><td>仕入れ価格</td><td><b>{price_str}</b></td></tr>
    <tr><td>プラットフォーム</td><td>{platform_label}</td></tr>
    </table>
    <p style="font-size:13px;color:#888">
    「出品する」を押すと以下が自動実行されます：<br>
    1. AIがタイトル・説明文・Item Specificsを生成<br>
    2. eShipにドラフト登録（出品数1）<br>
    3. eBayにドラフト作成（qty=0）<br>
    ※ 両方確認後に手動で公開
    </p>
    <form method="POST" action="/rare/list/{cid}">
    <button type="submit" style="background:#0066FF;color:white;border:none;
    padding:15px 40px;font-size:18px;border-radius:8px;margin-top:10px;
    cursor:pointer;width:100%">出品する（自動）</button>
    </form>
    <p style="margin-top:10px;text-align:center">
    <a href="{c["url"]}" target="_blank">仕入元を確認</a></p>
    </body></html>""")


@app.post("/rare/list/{cid}", response_class=HTMLResponse)
async def rare_list_execute(cid: str):
    c = await db.get_rare_candidate(cid)
    if not c:
        return HTMLResponse("<h2>候補が見つかりません</h2>", status_code=404)

    result = await create_ebay_listing_from_rare_candidate(cid)

    if result.get("status") == "ok":
        sku = result.get("sku", "")
        listing_id = result.get("listing_id", "")
        eship_link = "https://eship-tool.com/inventories"
        ebay_link = (
            f"https://www.ebay.com/itm/{listing_id}"
            if listing_id
            else "https://www.ebay.com/sh/lst/active"
        )
        return HTMLResponse(f"""
        <html><head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script>
        window.onload = function() {{
            window.open('{eship_link}', '_blank');
            setTimeout(function() {{ window.open('{ebay_link}', '_blank'); }}, 1000);
        }};
        </script>
        </head>
        <body style="font-family:sans-serif;padding:20px;text-align:center;max-width:500px;margin:0 auto">
        <h2 style="color:#1DB446">出品処理完了</h2>
        <p>SKU: <b>{sku}</b></p>
        <p style="font-size:14px;color:#666">{result.get("title", "")[:60]}</p>
        <table style="margin:15px auto;text-align:left">
        <tr><td>eShip:</td><td><span style="color:#FF6B35">バックグラウンド登録中</span></td></tr>
        <tr><td>eBay:</td><td>{'<span style="color:#1DB446">出品作成済（qty=0）</span>' if listing_id else '<span style="color:#e74c3c">作成失敗</span>'}</td></tr>
        </table>
        <div style="display:flex;gap:10px;justify-content:center;margin-top:20px">
        <a href="{eship_link}" target="_blank" style="background:#FF6B35;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:bold">eShipを確認</a>
        <a href="{ebay_link}" target="_blank" style="background:#0064D2;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:bold">eBay出品を確認</a>
        </div>
        <p style="color:#888;font-size:12px;margin-top:15px">※ 新しいタブでeShipとeBayが自動で開きます</p>
        </body></html>""")

    return HTMLResponse(f"""
    <html><body style="font-family:sans-serif;padding:20px;text-align:center">
    <h2 style="color:#e74c3c">エラー</h2>
    <p>{result.get("message", "Unknown error")}</p>
    <p><a href="/rare/list/{cid}">再試行</a></p>
    </body></html>""")


@app.get("/rare/eship/{cid}", response_class=HTMLResponse)
async def rare_eship_page(cid: str):
    c = await db.get_rare_candidate(cid)
    if not c:
        return HTMLResponse("<h2>候補が見つかりません</h2>", status_code=404)
    if c["status"] == "eshipped":
        return HTMLResponse("<h2 style='color:#1DB446'>✅ eShip登録済み</h2>")
    price_str = f"¥{c['price_jpy']:,}" if c["price_jpy"] else "価格不明"
    return HTMLResponse(f"""<html><body style="font-family:sans-serif;padding:20px;text-align:center">
    <h2>eShip登録確認</h2>
    <p style="font-size:14px;color:#666">{c["title"][:80]}</p>
    <p><b>{price_str}</b></p>
    <form method="POST" action="/rare/eship/{cid}">
    <button type="submit" style="background:#1DB446;color:white;border:none;
    padding:15px 40px;font-size:18px;border-radius:8px;margin-top:15px;cursor:pointer">
    eShipに登録する</button>
    </form>
    <p style="margin-top:10px"><a href="{c["url"]}" target="_blank">商品ページを確認</a></p>
    </body></html>""")


@app.post("/rare/eship/{cid}", response_class=HTMLResponse)
async def rare_eship_execute(cid: str):
    from eship import update_eship_item

    c = await db.get_rare_candidate(cid)
    if not c:
        return HTMLResponse("<h2>候補が見つかりません</h2>", status_code=404)
    result = await update_eship_item(
        ebay_title=c["title"],
        supplier_url=c["url"],
        purchase_price=c["price_jpy"] or 0,
        platform=c["platform"],
        set_quantity=1,
        sku="",
    )
    if result.get("status") == "ok":
        await db.update_rare_status(cid, "eshipped")
        return HTMLResponse(
            f"<h2 style='color:#1DB446'>✅ eShip登録完了！</h2><p>{c['title'][:60]}</p>"
        )
    return HTMLResponse(
        f"<h2 style='color:#e74c3c'>❌ 登録失敗</h2><p>{result.get('message', '')}</p><p><a href='/rare/eship/{cid}'>再試行</a></p>"
    )


@app.get("/rare/reject/{cid}", response_class=HTMLResponse)
async def rare_reject(cid: str):
    c = await db.get_rare_candidate(cid)
    if not c:
        return HTMLResponse("<h2>候補が見つかりません</h2>", status_code=404)
    await db.update_rare_status(cid, "rejected")
    return HTMLResponse(
        f"<h2 style='color:#888'>見送りました</h2><p>{c['title'][:60]}</p>"
    )


if __name__ == "__main__":
    import uvicorn
    import os

    reload = os.environ.get("DEV", "") == "1"
    uvicorn.run("app:app", host="0.0.0.0", port=config.PORT, reload=reload)
