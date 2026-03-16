import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
import database as db
from notifier import notify_line
from scrapers import ALL_SCRAPERS
from auto_sourcing import evaluate_listing, process_candidate, save_non_candidate
from discovery import (
    init_demand_tables, collect_demand_data, collect_from_own_sales,
    run_discovery_scan, create_ebay_listing_from_candidate,
)
from url_to_listing import url_to_listing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
templates = Jinja2Templates(directory="templates")

# Track scan status
scan_status = {"running": False, "last_run": None, "results": {}}


async def run_scan():
    """Run a full scan across all platforms for all active keywords."""
    if scan_status["running"]:
        logger.info("Scan already running, skipping")
        return

    scan_status["running"] = True
    keywords = await db.get_keywords(active_only=True)
    new_count = 0

    try:
        for kw in keywords:
            keyword_name = kw["name"]
            keyword_id = kw["id"]

            # Run all scrapers concurrently for this keyword
            tasks = [scraper.search(keyword_name) for scraper in ALL_SCRAPERS]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for scraper, result in zip(ALL_SCRAPERS, results):
                if isinstance(result, Exception):
                    logger.error(f"[{scraper.platform}] {keyword_name}: {result}")
                    continue

                # Relevance filter: all keyword words must appear in title
                kw_words = keyword_name.lower().split()
                filtered = [
                    item for item in result
                    if all(w in item.title.lower() for w in kw_words)
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
                        new_count += 1

                        if config.AUTO_SOURCE_MODE != "off":
                            try:
                                listing_data = {
                                    "platform": item.platform,
                                    "title": item.title,
                                    "price": item.price,
                                    "url": item.url,
                                    "external_id": item.external_id,
                                }
                                candidate, reason = await evaluate_listing(
                                    keyword_name, listing_data,
                                )
                                if candidate:
                                    await process_candidate(candidate, 0)
                                elif reason not in ("price_zero", "accessory"):
                                    # Save rejection for dashboard review (no LINE notification)
                                    await save_non_candidate(listing_data, reason)
                            except Exception as e:
                                logger.error(f"Auto-sourcing error: {e}")
                        else:
                            await notify_line(
                                item.platform, item.title, item.price, item.url
                            )

            # Small delay between keywords to be respectful
            await asyncio.sleep(1)

    except Exception as e:
        logger.error(f"Scan error: {e}")
    finally:
        scan_status["running"] = False
        from datetime import datetime
        scan_status["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Scan complete. {new_count} new listings found.")


async def refresh_eship_cache():
    """Refresh eShip profit cache periodically."""
    try:
        from eship import fetch_eship_profits
        profits = await fetch_eship_profits()
        logger.info(f"eShip cache refreshed: {len(profits)} items")
    except Exception as e:
        logger.error(f"eShip cache refresh failed: {e}")


async def run_demand_update():
    """Periodic demand DB update + discovery scan."""
    try:
        count = await collect_demand_data(max_queries=20)
        own = await collect_from_own_sales()
        logger.info(f"Demand update: {count} eBay items, {own} own sales")
    except Exception as e:
        logger.error(f"Demand update error: {e}")

    try:
        found = await run_discovery_scan(max_items=30)
        logger.info(f"Discovery scan: {found} candidates")
    except Exception as e:
        logger.error(f"Discovery scan error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    await init_demand_tables()
    scheduler.add_job(
        run_scan, "interval",
        minutes=config.CHECK_INTERVAL_MINUTES,
        id="main_scan",
        max_instances=1,
    )
    scheduler.add_job(
        refresh_eship_cache, "interval",
        hours=1,
        id="eship_cache_refresh",
        max_instances=1,
    )
    scheduler.add_job(
        run_demand_update, "interval",
        hours=6,
        id="demand_update",
        max_instances=1,
    )
    scheduler.start()
    logger.info(f"Scheduler started (interval: {config.CHECK_INTERVAL_MINUTES}min)")
    # Run initial tasks
    asyncio.create_task(refresh_eship_cache())
    asyncio.create_task(run_scan())
    # Delay discovery to avoid overwhelming startup
    asyncio.create_task(_delayed_discovery())
    yield
    scheduler.shutdown()


async def _delayed_discovery():
    """Run discovery scan after a delay to let main scan start first."""
    await asyncio.sleep(300)  # 5 min delay
    await run_demand_update()


app = FastAPI(title="Deal Watcher", lifespan=lifespan)


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
    return templates.TemplateResponse("index.html", {
        "request": request,
        "keywords": keywords,
        "groups": groups,
        "kw_count": kw_count,
        "listing_count": listing_count,
        "hidden_count": hidden_count,
        "scan_status": scan_status,
        "interval": config.CHECK_INTERVAL_MINUTES,
    })


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
        cur = await conn.execute("SELECT * FROM eship_candidates WHERE id = ?", (candidate_id,))
        candidate = await cur.fetchone()

    if not candidate:
        return HTMLResponse("<h2>候補が見つかりません</h2>", status_code=404)

    c = dict(candidate)
    if c["status"] == "done":
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:20px;text-align:center">
        <h2 style="color:#1DB446">✅ 登録済み</h2>
        <p>{c['ebay_title'][:60]}</p>
        <p>既にeShipに登録されています</p>
        </body></html>""")

    return HTMLResponse(f"""
    <html><body style="font-family:sans-serif;padding:20px;text-align:center">
    <h2>eShip登録確認</h2>
    <p style="font-size:14px;color:#666">{c['ebay_title'][:60]}</p>
    <table style="margin:10px auto;text-align:left">
    <tr><td>仕入れ価格</td><td><b>¥{c['source_price']:,}</b></td></tr>
    <tr><td>eBay価格</td><td>${c['ebay_price_usd']:,.0f}</td></tr>
    <tr><td>見込み利益</td><td style="color:#1DB446"><b>¥{c['profit_jpy']:,}</b></td></tr>
    <tr><td>仕入元</td><td>{c['source_platform']}</td></tr>
    </table>
    <form method="POST" action="/eship/register/{candidate_id}">
    <button type="submit" style="background:#1DB446;color:white;border:none;
    padding:15px 40px;font-size:18px;border-radius:8px;margin-top:15px;cursor:pointer">
    eShipに登録する</button>
    </form>
    <p style="margin-top:10px"><a href="{c['source_url']}" target="_blank">商品ページを確認</a></p>
    </body></html>""")


@app.post("/eship/register/{candidate_id}", response_class=HTMLResponse)
async def eship_register_execute(candidate_id: str):
    """Execute eShip registration from one-tap button."""
    import aiosqlite
    from eship import update_eship_item

    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM eship_candidates WHERE id = ?", (candidate_id,))
        candidate = await cur.fetchone()

    if not candidate:
        return HTMLResponse("<h2>候補が見つかりません</h2>", status_code=404)

    c = dict(candidate)
    if c["status"] == "done":
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:20px;text-align:center">
        <h2 style="color:#1DB446">✅ 既に登録済み</h2>
        <p>{c['ebay_title'][:60]}</p>
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
            await conn.execute("UPDATE eship_candidates SET status = 'done' WHERE id = ?", (candidate_id,))
            await conn.commit()

        # Update agent.db quantity
        from auto_sourcing import _update_agent_qty
        _update_agent_qty(c["ebay_title"])

        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:20px;text-align:center">
        <h2 style="color:#1DB446">✅ eShip登録完了！</h2>
        <p>{c['ebay_title'][:60]}</p>
        <p>仕入¥{c['source_price']:,} → 見込み利益¥{c['profit_jpy']:,}</p>
        </body></html>""")
    else:
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:20px;text-align:center">
        <h2 style="color:#e74c3c">❌ 登録失敗</h2>
        <p>{result.get('message', 'Unknown error')}</p>
        <p><a href="/eship/register/{candidate_id}">再試行</a></p>
        </body></html>""")


# --- Candidate Reject (learning) ---

@app.get("/candidate/reject/{candidate_id}", response_class=HTMLResponse)
async def candidate_reject_page(candidate_id: str):
    """Show rejection form for a sourcing candidate."""
    import aiosqlite
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM eship_candidates WHERE id = ?", (candidate_id,))
        candidate = await cur.fetchone()

    if not candidate:
        return HTMLResponse("<h2>候補が見つかりません</h2>", status_code=404)

    c = dict(candidate)
    if c["status"] == "rejected":
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:20px;text-align:center">
        <h2 style="color:#e74c3c">見送り済み</h2>
        <p>{c['ebay_title'][:60]}</p>
        <p>キーワード: <b>{c.get('reject_keywords', '')}</b></p>
        <p>理由: {c.get('reject_note', '')}</p>
        </body></html>""")

    return HTMLResponse(f"""
    <html><body style="font-family:sans-serif;padding:20px;max-width:500px;margin:0 auto">
    <h2 style="color:#e74c3c">見送り理由を入力</h2>
    <p style="font-size:14px;color:#666">{c['ebay_title'][:80]}</p>
    <table style="margin:10px 0;text-align:left;width:100%">
    <tr><td>仕入れ価格</td><td><b>¥{c['source_price']:,}</b></td></tr>
    <tr><td>eBay価格</td><td>${c['ebay_price_usd']:,.0f}</td></tr>
    <tr><td>見込み利益</td><td>¥{c['profit_jpy']:,}</td></tr>
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
    <a href="{c['source_url']}" target="_blank">商品ページを確認</a></p>
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
        cur = await conn.execute("SELECT * FROM eship_candidates WHERE id = ?", (candidate_id,))
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
    <p>{dict(candidate)['ebay_title'][:60]}</p>
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
        cur = await conn.execute("SELECT * FROM learning_data WHERE id = ?", (feedback_id,))
        item = await cur.fetchone()

    if not item:
        return HTMLResponse("<h2>データが見つかりません</h2>", status_code=404)

    d = dict(item)
    if d["user_action"] == "sourced":
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:20px;text-align:center">
        <h2 style="color:#f39c12">📝 フィードバック済み</h2>
        <p>{d['listing_title'][:60]}</p>
        <p>ご意見ありがとうございます！学習データとして保存されています。</p>
        </body></html>""")

    reason_label = REJECT_REASONS.get(d["rejection_reason"], d["rejection_reason"])
    price = d["listing_price"] or 0

    return HTMLResponse(f"""
    <html><body style="font-family:sans-serif;padding:20px;max-width:500px;margin:0 auto">
    <h2 style="color:#f39c12">📝 仕入れフィードバック</h2>
    <p style="font-size:14px;color:#666">{d['listing_title'][:80]}</p>
    <table style="margin:10px 0;text-align:left;width:100%">
    <tr><td>価格</td><td><b>¥{price:,}</b></td></tr>
    <tr><td>プラットフォーム</td><td>{d['platform']}</td></tr>
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
    <a href="{d['url']}" target="_blank">商品ページを確認</a></p>
    </body></html>""")


@app.post("/feedback/{feedback_id}", response_class=HTMLResponse)
async def feedback_submit(feedback_id: str, note: str = Form("")):
    """Save user feedback on a non-candidate listing."""
    import aiosqlite
    async with aiosqlite.connect(config.DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM learning_data WHERE id = ?", (feedback_id,))
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
    <p>{dict(item)['listing_title'][:60]}</p>
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
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:20px;text-align:center">
        <h2 style="color:#0066FF">出品済み</h2>
        <p>{c['brand']} {c['model']}</p>
        <p>既にeShip + eBayに登録されています</p>
        </body></html>""")

    product_name = f"{c['brand']} {c['model']}".strip() or c['source_title'][:40]

    return HTMLResponse(f"""
    <html><body style="font-family:sans-serif;padding:20px;max-width:500px;margin:0 auto">
    <h2 style="color:#0066FF">新規出品確認</h2>
    <p style="font-weight:bold;font-size:16px">{product_name}</p>
    <p style="font-size:13px;color:#666">{c['source_title'][:80]}</p>
    <table style="margin:10px 0;text-align:left;width:100%">
    <tr><td>仕入れ価格</td><td><b>¥{c['source_price']:,}</b></td></tr>
    <tr><td>eBay相場</td><td>${c['ebay_est_price_usd']:,.0f}</td></tr>
    <tr><td>見込み利益</td><td style="color:#1DB446"><b>¥{c['est_profit_jpy']:,}</b></td></tr>
    <tr><td>状態</td><td>{c['source_condition'] or '不明'}</td></tr>
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
    <a href="{c['source_url']}" target="_blank">仕入元を確認</a></p>
    </body></html>""")


@app.post("/discovery/approve/{candidate_id}", response_class=HTMLResponse)
async def discovery_approve_execute(candidate_id: str):
    """Execute auto-listing pipeline for a discovery candidate."""
    result = await create_ebay_listing_from_candidate(candidate_id)

    if result.get("status") == "ok":
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:20px;text-align:center">
        <h2 style="color:#1DB446">出品処理完了</h2>
        <p>SKU: <b>{result.get('sku', '')}</b></p>
        <p>{result.get('title', '')[:60]}</p>
        <p>eShip: {'登録済' if result.get('eship_registered') else '未登録'}</p>
        <p>eBay: ドラフト作成済 (Offer ID: {result.get('offer_id', '')})</p>
        <p style="color:#888;font-size:13px">
        eBay Seller Hub でドラフトを確認し、写真を追加して公開してください。</p>
        </body></html>""")
    else:
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:20px;text-align:center">
        <h2 style="color:#e74c3c">エラー</h2>
        <p>{result.get('message', 'Unknown error')}</p>
        <p><a href="/discovery/approve/{candidate_id}">再試行</a></p>
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
    product_name = f"{c['brand']} {c['model']}".strip() or c['source_title'][:40]

    return HTMLResponse(f"""
    <html><body style="font-family:sans-serif;padding:20px;max-width:500px;margin:0 auto">
    <h2 style="color:#e74c3c">見送り理由を入力</h2>
    <p style="font-weight:bold">{product_name}</p>
    <p style="font-size:13px;color:#666">{c['source_title'][:80]}</p>
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
    <p>除外キーワード: <b>{keywords.strip() or 'なし'}</b></p>
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
            <td style="padding:8px;border-bottom:1px solid #eee"><b>{result['sku']}</b></td></tr>
        <tr><td style="padding:8px;border-bottom:1px solid #eee">タイトル</td>
            <td style="padding:8px;border-bottom:1px solid #eee">{result['title'][:60]}</td></tr>
        <tr><td style="padding:8px;border-bottom:1px solid #eee">eBay価格</td>
            <td style="padding:8px;border-bottom:1px solid #eee"><b>${result['price_usd']:,.2f}</b></td></tr>
        <tr><td style="padding:8px;border-bottom:1px solid #eee">見込み利益</td>
            <td style="padding:8px;border-bottom:1px solid #eee;color:#1DB446">
            <b>¥{result['profit_jpy']:,}</b> ({result['margin']:.0%})</td></tr>
        <tr><td style="padding:8px;border-bottom:1px solid #eee">コンディション</td>
            <td style="padding:8px;border-bottom:1px solid #eee">{result['condition']}</td></tr>
        <tr><td style="padding:8px;border-bottom:1px solid #eee">画像数</td>
            <td style="padding:8px;border-bottom:1px solid #eee">{result['image_count']}</td></tr>
        <tr><td style="padding:8px;border-bottom:1px solid #eee">Item Specifics</td>
            <td style="padding:8px;border-bottom:1px solid #eee">{result['specs_count']}項目</td></tr>
        <tr><td style="padding:8px;border-bottom:1px solid #eee">eShip</td>
            <td style="padding:8px;border-bottom:1px solid #eee">
            {'登録済' if result['eship_registered'] else '未登録'}</td></tr>
        <tr><td style="padding:8px;border-bottom:1px solid #eee">eBay</td>
            <td style="padding:8px;border-bottom:1px solid #eee">
            {'ドラフト作成済' if result['ebay_created'] else '未作成'}
            {f" (Offer: {result['offer_id']})" if result.get('offer_id') else ''}</td></tr>
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
        <p>{result.get('message', 'Unknown error')}</p>
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


@app.get("/api/status")
async def api_status():
    return scan_status


@app.get("/api/listings")
async def api_listings(limit: int = 50):
    listings = await db.get_recent_listings(limit=limit)
    return [dict(row) for row in listings]


if __name__ == "__main__":
    import uvicorn
    import os
    reload = os.environ.get("DEV", "") == "1"
    uvicorn.run("app:app", host="0.0.0.0", port=config.PORT, reload=reload)
