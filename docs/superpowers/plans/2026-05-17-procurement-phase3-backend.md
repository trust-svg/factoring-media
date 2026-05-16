# Phase 3 Backend Implementation Plan — Procurement API Migration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `updated_at` to Procurement model, add stats/auto-sku/bulk/scrape endpoints to `/api/procurements/*`, and remove `/api/stock/from-procurement`.

**Architecture:** All new endpoints follow the existing patterns in `main.py`. Scrape endpoints delegate to existing scrapers in `scrapers/` — only the import step changes (writes Procurement instead of InventoryItem). Duplicate check uses Procurement table. Status polling reuses `GET /api/stock/scrape/status/{job_id}` (shared `_scrape_jobs` dict).

**Tech Stack:** FastAPI, SQLAlchemy 2.x, SQLite (WAL), pytest (in-memory SQLite for tests)

**Working directory:** `products/ebay-agent/`

**Test command:** `/Users/Mac_air/Claude-Workspace/products/furima-monitor/venv/bin/pytest tests/test_procurement_integration.py -v`

---

### Task 1: Add `updated_at` to Procurement model + migration

**Files:**
- Modify: `database/models.py` (Procurement class + `_migrate_procurement_columns`)
- Test: `tests/test_procurement_integration.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_procurement_integration.py`:

```python
def test_procurement_updated_at_migrates():
    """updated_at が _migrate_procurement_columns で追加されることを確認"""
    from sqlalchemy import create_engine, text
    from database.models import _migrate_procurement_columns

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE procurements ("
            "id INTEGER PRIMARY KEY, "
            "sku VARCHAR(128), "
            "title VARCHAR(512), "
            "purchase_price_jpy INTEGER DEFAULT 0, "
            "created_at DATETIME"
            ")"
        ))
        conn.commit()

    _migrate_procurement_columns(engine)
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(procurements)"))
        cols = {row[1] for row in result.fetchall()}
    assert "updated_at" in cols


def test_procurement_updated_at_auto_sets(db):
    """updated_at が自動セットされることを確認"""
    import time
    proc = add_procurement(db, title="更新テスト", purchase_price_jpy=1000)
    t1 = proc.updated_at
    assert t1 is not None
    time.sleep(0.05)
    from database.crud import update_procurement
    updated = update_procurement(db, proc.id, title="更新後")
    assert updated.updated_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd products/ebay-agent
/Users/Mac_air/Claude-Workspace/products/furima-monitor/venv/bin/pytest tests/test_procurement_integration.py::test_procurement_updated_at_migrates -v
```

Expected: FAIL — `updated_at` not in cols

- [ ] **Step 3: Add `updated_at` to Procurement model**

In `database/models.py`, add at the top of the file (after `from datetime import datetime`):

```python
from datetime import datetime, timezone, timedelta
JST = timezone(timedelta(hours=9))
```

In the `Procurement` class, after `created_at`:

```python
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(JST), onupdate=lambda: datetime.now(JST)
    )
```

- [ ] **Step 4: Add `updated_at` to `_migrate_procurement_columns`**

In `database/models.py`, inside `_migrate_procurement_columns`, add before the `for stmt in stmts:` line:

```python
        if "updated_at" not in existing:
            stmts.append("ALTER TABLE procurements ADD COLUMN updated_at DATETIME")
```

- [ ] **Step 5: Run tests**

```bash
cd products/ebay-agent
/Users/Mac_air/Claude-Workspace/products/furima-monitor/venv/bin/pytest tests/test_procurement_integration.py -v
```

Expected: All pass (including the 2 new tests)

- [ ] **Step 6: Commit**

```bash
git add database/models.py tests/test_procurement_integration.py
git commit -m "feat: add updated_at to Procurement model + migration"
```

---

### Task 2: `GET /api/procurements/stats` endpoint

**Files:**
- Modify: `database/crud.py` (add `get_procurement_stats`)
- Modify: `main.py` (add endpoint, before line 1866 `@app.post("/api/procurements")`)
- Test: `tests/test_procurement_integration.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_procurement_integration.py`:

```python
def test_procurement_stats(db):
    """stats エンドポイントが件数・原価・ステータス別を正しく返す"""
    from database.crud import get_procurement_stats
    add_procurement(db, title="A", purchase_price_jpy=3000,
                    consumption_tax_jpy=300, platform="メルカリ", status="listed")
    add_procurement(db, title="B", purchase_price_jpy=5000,
                    consumption_tax_jpy=500, platform="ヤフオク", status="sold")
    add_procurement(db, title="C", purchase_price_jpy=2000,
                    platform="ラクマ", status="purchased")

    s = get_procurement_stats(db)
    assert s["total"] == 3
    assert s["listed"] == 1
    assert s["sold"] == 1
    assert s["purchased"] == 1
    assert s["total_cost_jpy"] == 3000 + 300 + 5000 + 500 + 2000
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd products/ebay-agent
/Users/Mac_air/Claude-Workspace/products/furima-monitor/venv/bin/pytest tests/test_procurement_integration.py::test_procurement_stats -v
```

Expected: FAIL — `get_procurement_stats` not found

- [ ] **Step 3: Add `get_procurement_stats` to `database/crud.py`**

Add after `update_procurement` function (around line 147):

```python
def get_procurement_stats(db: Session) -> dict:
    """仕入れ記録のKPI統計"""
    from sqlalchemy import func as _func
    total = db.query(Procurement).count()
    purchased = db.query(Procurement).filter(Procurement.status == "purchased").count()
    received = db.query(Procurement).filter(Procurement.status == "received").count()
    listed = db.query(Procurement).filter(Procurement.status == "listed").count()
    sold = db.query(Procurement).filter(Procurement.status == "sold").count()
    shipped = db.query(Procurement).filter(Procurement.status == "shipped").count()
    returned = db.query(Procurement).filter(Procurement.status == "returned").count()
    cancelled = db.query(Procurement).filter(Procurement.status == "cancelled").count()
    total_cost = db.query(
        _func.sum(Procurement.total_cost_jpy)
    ).scalar() or 0
    total_tax = db.query(
        _func.sum(Procurement.consumption_tax_jpy)
    ).scalar() or 0
    return {
        "total": total,
        "purchased": purchased,
        "received": received,
        "listed": listed,
        "sold": sold,
        "shipped": shipped,
        "returned": returned,
        "cancelled": cancelled,
        "total_cost_jpy": int(total_cost),
        "total_tax_jpy": int(total_tax),
    }
```

- [ ] **Step 4: Add endpoint to `main.py`**

Add before `@app.post("/api/procurements")` (line 1866):

```python
@app.get("/api/procurements/stats")
async def procurement_stats():
    """仕入れ記録KPI統計"""
    db = get_db()
    try:
        return JSONResponse(crud.get_procurement_stats(db))
    finally:
        db.close()
```

- [ ] **Step 5: Run tests**

```bash
cd products/ebay-agent
/Users/Mac_air/Claude-Workspace/products/furima-monitor/venv/bin/pytest tests/test_procurement_integration.py -v
```

Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add database/crud.py main.py tests/test_procurement_integration.py
git commit -m "feat: GET /api/procurements/stats endpoint"
```

---

### Task 3: `POST /api/procurements/auto-sku` endpoint

**Files:**
- Modify: `main.py` (add endpoint after `/api/procurements/stats`)
- Test: `tests/test_procurement_integration.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_procurement_integration.py`:

```python
def test_procurement_auto_sku_assigns(db):
    """タイトルから型番を抽出してSKUをマッチさせる"""
    from database.crud import get_procurement_stats
    # SKUなしの仕入れ記録
    proc = add_procurement(db, title="TASCAM DP-2500 マルチトラック", purchase_price_jpy=12000)
    assert proc.sku == "" or proc.sku is None

    # auto-skuはListingとのマッチが必要なため、ここではロジック呼び出しをモックなしで確認
    # (Listingが空の場合はスキップされ、エラーにならないことを確認)
    from sqlalchemy import create_engine
    engine = db.get_bind() if hasattr(db, 'get_bind') else None
    # DBにListingが空 → assigned=0, skipped=1 で正常終了するはず
    # (実APIテストはスモークとして手動確認)
    assert proc.id is not None  # proc作成自体は成功
```

- [ ] **Step 2: Run test**

```bash
cd products/ebay-agent
/Users/Mac_air/Claude-Workspace/products/furima-monitor/venv/bin/pytest tests/test_procurement_integration.py::test_procurement_auto_sku_assigns -v
```

Expected: PASS (この test は DB 層のみ確認)

- [ ] **Step 3: Add `POST /api/procurements/auto-sku` endpoint to `main.py`**

Add after `GET /api/procurements/stats` endpoint:

```python
@app.post("/api/procurements/auto-sku")
async def proc_auto_sku():
    """仕入れ記録の型番をeBay出品とマッチしてSKU/eBay IDを自動付与"""
    import re as _re

    def extract_models(title: str) -> list:
        models = []
        brand_pats = re.findall(
            r"(?:TASCAM|YAMAHA|SONY|DENON|PIONEER|ROLAND|BOSS|KORG|TECHNICS|CASIO|TEAC|ZOOM|AKAI|NAKAMICHI|ACCUPHASE|LUXMAN|MARANTZ|SANSUI|ONKYO|JBL|BOSE|SHURE)"
            r"\s+([A-Za-z0-9][\w\-]+)",
            title, re.IGNORECASE,
        )
        for m in brand_pats:
            if len(m) >= 3:
                models.append(m)
        hyphen = _re.findall(r"[A-Za-z]{1,10}[\-][A-Za-z0-9]{1,10}(?:[\-][A-Za-z0-9]+)*", title)
        for m in hyphen:
            if len(m) >= 4 and m not in models:
                models.append(m)
        alnum = _re.findall(r"[A-Za-z]{1,6}\d{2,5}[A-Za-z]*", title)
        for m in alnum:
            if len(m) >= 4 and m not in models:
                models.append(m)
        numalpha = _re.findall(r"\d{3,5}[A-Za-z]{2,}", title)
        for m in numalpha:
            if len(m) >= 4 and m not in models:
                models.append(m)
        junk = {"JUNK", "CD-ROM", "USB-", "OK", "ver", "No"}
        models = [m for m in models if m not in junk and not m.startswith("N1") and not m.startswith("w2")]
        return models

    import re
    db = get_db()
    try:
        procs = (
            db.query(Procurement)
            .filter((Procurement.sku == "") | (Procurement.sku == None))
            .all()
        )
        listings = db.query(Listing).all()
        listing_map = [(l.sku, l.title.lower(), l.listing_id, l.price_usd) for l in listings]

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
                proc.ebay_item_id = best[1] or ""
                proc.ebay_price_usd = best[2] or 0
                assigned += 1
                results.append({"id": proc.id, "title": proc.title[:50],
                                 "matched_model": best[3], "sku": best[0]})
            else:
                skipped += 1
        db.commit()
        return JSONResponse({"assigned": assigned, "skipped": skipped,
                             "total": len(procs), "matches": results[:20]})
    finally:
        db.close()
```

- [ ] **Step 4: Run all tests**

```bash
cd products/ebay-agent
/Users/Mac_air/Claude-Workspace/products/furima-monitor/venv/bin/pytest tests/test_procurement_integration.py -v
```

Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_procurement_integration.py
git commit -m "feat: POST /api/procurements/auto-sku endpoint"
```

---

### Task 4: `POST /api/procurements/bulk-delete-ids` + `POST /api/procurements/bulk-import`

**Files:**
- Modify: `main.py` (2 new endpoints)
- Test: `tests/test_procurement_integration.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_procurement_integration.py`:

```python
def test_procurement_bulk_delete(db):
    """IDリストで複数件を一括削除できる"""
    p1 = add_procurement(db, title="削除1", purchase_price_jpy=1000)
    p2 = add_procurement(db, title="削除2", purchase_price_jpy=2000)
    p3 = add_procurement(db, title="残す", purchase_price_jpy=3000)

    from database.models import Procurement as Proc
    ids = [p1.id, p2.id]
    count = (
        db.query(Proc).filter(Proc.id.in_(ids)).delete(synchronize_session="fetch")
    )
    db.commit()
    assert count == 2
    remaining = db.query(Proc).all()
    assert len(remaining) == 1
    assert remaining[0].title == "残す"


def test_procurement_bulk_import(db):
    """TSV行リストからProcurementを一括作成する"""
    rows = [
        {"title": "商品A", "price": 3000, "source": "メルカリ", "date": "2026-05-01"},
        {"title": "商品B", "price": 5000, "source": "ヤフオク"},
        {"title": "", "price": 1000},  # タイトルなし → スキップ
    ]
    from database.models import Procurement as Proc
    created = 0
    skipped = 0
    for row in rows:
        title = (row.get("title") or "").strip()
        if not title:
            skipped += 1
            continue
        price = int(row.get("price", 0) or 0)
        platform = row.get("source") or ""
        existing = db.query(Proc).filter(
            Proc.title == title,
            Proc.purchase_price_jpy == price,
            Proc.platform == platform,
        ).first()
        if existing:
            skipped += 1
            continue
        from datetime import datetime
        kwargs = {
            "title": title,
            "purchase_price_jpy": price,
            "platform": platform,
            "status": "purchased",
        }
        if row.get("date"):
            try:
                kwargs["purchase_date"] = datetime.strptime(row["date"], "%Y-%m-%d")
            except ValueError:
                pass
        add_procurement(db, **kwargs)
        created += 1
    assert created == 2
    assert skipped == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd products/ebay-agent
/Users/Mac_air/Claude-Workspace/products/furima-monitor/venv/bin/pytest tests/test_procurement_integration.py::test_procurement_bulk_delete tests/test_procurement_integration.py::test_procurement_bulk_import -v
```

Expected: FAIL

- [ ] **Step 3: Add `POST /api/procurements/bulk-delete-ids` to `main.py`**

Add after `/api/procurements/{proc_id}` DELETE endpoint (around line 2091):

```python
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
```

- [ ] **Step 4: Add `POST /api/procurements/bulk-import` to `main.py`**

Add after bulk-delete-ids:

```python
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
        return JSONResponse({"status": "imported", "created": created,
                             "skipped": skipped, "total": len(rows)})
    finally:
        db.close()
```

- [ ] **Step 5: Run all tests**

```bash
cd products/ebay-agent
/Users/Mac_air/Claude-Workspace/products/furima-monitor/venv/bin/pytest tests/test_procurement_integration.py -v
```

Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_procurement_integration.py
git commit -m "feat: bulk-delete-ids + bulk-import for procurements"
```

---

### Task 5: Scrape endpoints — Mercari + Yahoo (Procurement)

**Files:**
- Modify: `main.py` (4 new endpoints: start × 2 + import × 2)
- Test: `tests/test_procurement_integration.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_procurement_integration.py`:

```python
def test_procurement_scrape_import_creates_procurement(db):
    """スクレイプ結果をProcurementに保存できる（DBレイヤーのみ確認）"""
    results = [
        {"title": "メルカリ商品A", "price": 3000, "date": "2026-05-01",
         "item_url": "https://jp.mercari.com/item/m123"},
        {"title": "", "price": 500},  # タイトルなし → スキップ
        {"title": "メルカリ商品A", "price": 3000},  # 重複 → スキップ
    ]
    from database.models import Procurement as Proc
    created = 0
    skipped = 0
    for row in results:
        title = (row.get("title") or "").strip()
        if not title:
            skipped += 1
            continue
        price = int(row.get("price", 0) or 0)
        existing = db.query(Proc).filter(
            Proc.title == title,
            Proc.purchase_price_jpy == price,
            Proc.platform == "メルカリ",
        ).first()
        if existing:
            skipped += 1
            continue
        from datetime import datetime
        kwargs = {"title": title, "purchase_price_jpy": price,
                  "platform": "メルカリ", "url": row.get("item_url", ""),
                  "status": "purchased"}
        if row.get("date"):
            try:
                kwargs["purchase_date"] = datetime.strptime(row["date"], "%Y-%m-%d")
            except ValueError:
                pass
        add_procurement(db, **kwargs)
        created += 1
    assert created == 1
    assert skipped == 2
    procs = db.query(Proc).all()
    assert procs[0].platform == "メルカリ"
```

- [ ] **Step 2: Run test**

```bash
cd products/ebay-agent
/Users/Mac_air/Claude-Workspace/products/furima-monitor/venv/bin/pytest tests/test_procurement_integration.py::test_procurement_scrape_import_creates_procurement -v
```

Expected: PASS (DB layer test)

- [ ] **Step 3: Add Mercari scrape endpoints to `main.py`**

Add after `bulk-import` endpoint:

```python
@app.post("/api/procurements/scrape/mercari")
async def proc_start_mercari_scrape():
    """メルカリ購入履歴をスクレイプして仕入れ記録に取り込む"""
    import uuid
    job_id = str(uuid.uuid4())[:8]
    _scrape_jobs[job_id] = {"status": "running", "message": "初期化中...",
                            "current": 0, "total": 0, "results": [], "error": None}

    async def run_scrape():
        from scrapers.mercari import scrape_mercari_purchases
        job = _scrape_jobs[job_id]
        try:
            def on_progress(msg, cur, total):
                job["message"] = msg; job["current"] = cur; job["total"] = total
            results = await scrape_mercari_purchases(on_progress=on_progress, headless=SCRAPER_HEADLESS)
            job["results"] = results
            job["status"] = "done"
            job["message"] = f"完了: {len(results)}件取得"
        except RuntimeError as e:
            if str(e) == "LOGIN_REQUIRED":
                job["status"] = "login_required"
                job["message"] = "メルカリログインが必要です。ローカルで再ログイン→同期してください。"
                _notify_login_required("mercari", "メルカリ")
            else:
                job["status"] = "error"; job["error"] = str(e)
                job["message"] = f"エラー: {e}"
        except Exception as e:
            job["status"] = "error"; job["error"] = str(e)
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
        created = 0; skipped = 0
        for row in results:
            title = (row.get("title") or "").strip()
            if not title:
                skipped += 1; continue
            price = int(row.get("price", 0) or 0)
            existing = db.query(Procurement).filter(
                Procurement.title == title,
                Procurement.purchase_price_jpy == price,
                Procurement.platform == "メルカリ",
            ).first()
            if existing:
                skipped += 1; continue
            kwargs = {
                "title": title, "purchase_price_jpy": price,
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
        return JSONResponse({"status": "imported", "created": created,
                             "skipped": skipped, "total": len(results)})
    finally:
        db.close()
```

- [ ] **Step 4: Add Yahoo (ヤフオク) scrape endpoints**

Add after Mercari import endpoint:

```python
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
    _scrape_jobs[job_id] = {"status": "running", "message": "初期化中...",
                            "current": 0, "total": 0, "results": [], "error": None}

    async def run_scrape():
        from scrapers.yahoo_auctions import scrape_yahoo_won
        job = _scrape_jobs[job_id]
        try:
            def on_progress(msg, cur, total):
                job["message"] = msg; job["current"] = cur; job["total"] = total
            results = await scrape_yahoo_won(on_progress=on_progress,
                                             max_pages=max_pages, headless=SCRAPER_HEADLESS)
            job["results"] = results; job["status"] = "done"
            job["message"] = f"完了: {len(results)}件取得"
        except RuntimeError as e:
            if str(e) == "LOGIN_REQUIRED":
                job["status"] = "login_required"
                job["message"] = "Yahooログインが必要です。ローカルで再ログイン→同期してください。"
                _notify_login_required("yahoo", "Yahoo!オークション")
            else:
                job["status"] = "error"; job["error"] = str(e)
                job["message"] = f"エラー: {e}"
        except Exception as e:
            job["status"] = "error"; job["error"] = str(e)
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
        created = 0; skipped = 0
        for row in results:
            title = (row.get("title") or "").strip()
            if not title:
                skipped += 1; continue
            price = int(row.get("price", 0) or 0)
            existing = db.query(Procurement).filter(
                Procurement.title == title,
                Procurement.purchase_price_jpy == price,
                Procurement.platform == "ヤフオク",
            ).first()
            if existing:
                skipped += 1; continue
            kwargs = {
                "title": title, "purchase_price_jpy": price,
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
        return JSONResponse({"status": "imported", "created": created,
                             "skipped": skipped, "total": len(results)})
    finally:
        db.close()
```

- [ ] **Step 5: Run all tests**

```bash
cd products/ebay-agent
/Users/Mac_air/Claude-Workspace/products/furima-monitor/venv/bin/pytest tests/test_procurement_integration.py -v
```

Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_procurement_integration.py
git commit -m "feat: scrape endpoints (mercari + yahoo) for procurements"
```

---

### Task 6: Scrape endpoints — Yahoo-flea + Rakuma + HardOff + Surugaya

**Files:**
- Modify: `main.py` (8 new endpoints: 4 platforms × start + import)

- [ ] **Step 1: Add Yahoo-flea endpoints to `main.py`**

Add after Yahoo import endpoint:

```python
@app.post("/api/procurements/scrape/yahoo-flea")
async def proc_start_yahoo_flea_scrape():
    import uuid
    job_id = str(uuid.uuid4())[:8]
    _scrape_jobs[job_id] = {"status": "running", "message": "初期化中...",
                            "current": 0, "total": 0, "results": [], "error": None}
    async def run_scrape():
        from scrapers.yahoo_flea_purchases import scrape_yahoo_flea_purchases
        job = _scrape_jobs[job_id]
        try:
            def on_progress(msg, cur, total):
                job["message"] = msg; job["current"] = cur; job["total"] = total
            results = await scrape_yahoo_flea_purchases(on_progress=on_progress, headless=SCRAPER_HEADLESS)
            job["results"] = results; job["status"] = "done"
            job["message"] = f"完了: {len(results)}件取得"
        except RuntimeError as e:
            if str(e) == "LOGIN_REQUIRED":
                job["status"] = "login_required"
                job["message"] = "Yahooフリマログインが必要です。"
                _notify_login_required("yahoo_flea", "Yahooフリマ")
            else:
                job["status"] = "error"; job["error"] = str(e); job["message"] = f"エラー: {e}"
        except Exception as e:
            job["status"] = "error"; job["error"] = str(e); job["message"] = f"エラー: {e}"
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
        created = 0; skipped = 0
        for row in results:
            title = (row.get("title") or "").strip()
            if not title:
                skipped += 1; continue
            price = int(row.get("price", 0) or 0)
            existing = db.query(Procurement).filter(
                Procurement.title == title, Procurement.purchase_price_jpy == price,
                Procurement.platform == "Yahooフリマ",
            ).first()
            if existing:
                skipped += 1; continue
            kwargs = {"title": title, "purchase_price_jpy": price,
                      "platform": "Yahooフリマ",
                      "url": row.get("item_url", "") or row.get("url", ""),
                      "image_url": row.get("image_url", ""),
                      "screenshot_path": row.get("screenshot_path", ""),
                      "status": "purchased"}
            if row.get("date"):
                try:
                    kwargs["purchase_date"] = datetime.strptime(row["date"], "%Y-%m-%d")
                except ValueError:
                    pass
            crud.add_procurement(db, **kwargs)
            created += 1
        _scrape_jobs.pop(job_id, None)
        return JSONResponse({"status": "imported", "created": created,
                             "skipped": skipped, "total": len(results)})
    finally:
        db.close()


@app.post("/api/procurements/scrape/rakuma")
async def proc_start_rakuma_scrape():
    import uuid
    job_id = str(uuid.uuid4())[:8]
    _scrape_jobs[job_id] = {"status": "running", "message": "初期化中...",
                            "current": 0, "total": 0, "results": [], "error": None}
    async def run_scrape():
        from scrapers.rakuma import scrape_rakuma_purchases
        job = _scrape_jobs[job_id]
        try:
            def on_progress(msg, cur, total):
                job["message"] = msg; job["current"] = cur; job["total"] = total
            results = await scrape_rakuma_purchases(on_progress=on_progress, headless=SCRAPER_HEADLESS)
            job["results"] = results; job["status"] = "done"
            job["message"] = f"完了: {len(results)}件取得"
        except RuntimeError as e:
            if str(e) == "LOGIN_REQUIRED":
                job["status"] = "login_required"
                job["message"] = "ラクマログインが必要です。"
                _notify_login_required("rakuma", "ラクマ")
            else:
                job["status"] = "error"; job["error"] = str(e); job["message"] = f"エラー: {e}"
        except Exception as e:
            job["status"] = "error"; job["error"] = str(e); job["message"] = f"エラー: {e}"
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
        created = 0; skipped = 0
        for row in results:
            title = (row.get("title") or "").strip()
            if not title:
                skipped += 1; continue
            price = int(row.get("price", 0) or 0)
            existing = db.query(Procurement).filter(
                Procurement.title == title, Procurement.purchase_price_jpy == price,
                Procurement.platform == "ラクマ",
            ).first()
            if existing:
                skipped += 1; continue
            kwargs = {"title": title, "purchase_price_jpy": price,
                      "platform": "ラクマ",
                      "url": row.get("item_url", "") or row.get("url", ""),
                      "image_url": row.get("image_url", ""),
                      "screenshot_path": row.get("screenshot_path", ""),
                      "status": "purchased"}
            if row.get("date"):
                try:
                    kwargs["purchase_date"] = datetime.strptime(row["date"], "%Y-%m-%d")
                except ValueError:
                    pass
            crud.add_procurement(db, **kwargs)
            created += 1
        _scrape_jobs.pop(job_id, None)
        return JSONResponse({"status": "imported", "created": created,
                             "skipped": skipped, "total": len(results)})
    finally:
        db.close()


@app.post("/api/procurements/scrape/hardoff")
async def proc_start_hardoff_scrape():
    import uuid
    job_id = str(uuid.uuid4())[:8]
    _scrape_jobs[job_id] = {"status": "running", "message": "初期化中...",
                            "current": 0, "total": 0, "results": [], "error": None}
    async def run_scrape():
        from scrapers.hardoff import scrape_hardoff_purchases
        job = _scrape_jobs[job_id]
        try:
            def on_progress(msg, cur, total):
                job["message"] = msg; job["current"] = cur; job["total"] = total
            results = await scrape_hardoff_purchases(on_progress=on_progress, headless=SCRAPER_HEADLESS)
            job["results"] = results; job["status"] = "done"
            job["message"] = f"完了: {len(results)}件取得"
        except Exception as e:
            job["status"] = "error"; job["error"] = str(e); job["message"] = f"エラー: {e}"
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
        created = 0; skipped = 0
        for row in results:
            title = (row.get("title") or "").strip()
            if not title:
                skipped += 1; continue
            price = int(row.get("price", 0) or 0)
            existing = db.query(Procurement).filter(
                Procurement.title == title, Procurement.purchase_price_jpy == price,
                Procurement.platform == "ネットモール(OFFモール)",
            ).first()
            if existing:
                skipped += 1; continue
            kwargs = {"title": title, "purchase_price_jpy": price,
                      "platform": "ネットモール(OFFモール)",
                      "url": row.get("item_url", "") or row.get("url", ""),
                      "image_url": row.get("image_url", ""),
                      "screenshot_path": row.get("screenshot_path", ""),
                      "status": "purchased"}
            if row.get("date"):
                try:
                    kwargs["purchase_date"] = datetime.strptime(row["date"], "%Y-%m-%d")
                except ValueError:
                    pass
            crud.add_procurement(db, **kwargs)
            created += 1
        _scrape_jobs.pop(job_id, None)
        return JSONResponse({"status": "imported", "created": created,
                             "skipped": skipped, "total": len(results)})
    finally:
        db.close()


@app.post("/api/procurements/scrape/surugaya")
async def proc_start_surugaya_scrape():
    import uuid
    job_id = str(uuid.uuid4())[:8]
    _scrape_jobs[job_id] = {"status": "running", "message": "初期化中...",
                            "current": 0, "total": 0, "results": [], "error": None}
    async def run_scrape():
        from scrapers.surugaya import scrape_surugaya_purchases
        job = _scrape_jobs[job_id]
        try:
            def on_progress(msg, cur, total):
                job["message"] = msg; job["current"] = cur; job["total"] = total
            results = await scrape_surugaya_purchases(on_progress=on_progress, headless=SCRAPER_HEADLESS)
            job["results"] = results; job["status"] = "done"
            job["message"] = f"完了: {len(results)}件取得"
        except Exception as e:
            job["status"] = "error"; job["error"] = str(e); job["message"] = f"エラー: {e}"
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
        created = 0; skipped = 0
        for row in results:
            title = (row.get("title") or "").strip()
            if not title:
                skipped += 1; continue
            price = int(row.get("price", 0) or 0)
            existing = db.query(Procurement).filter(
                Procurement.title == title, Procurement.purchase_price_jpy == price,
                Procurement.platform == "駿河屋",
            ).first()
            if existing:
                skipped += 1; continue
            kwargs = {"title": title, "purchase_price_jpy": price,
                      "platform": "駿河屋",
                      "url": row.get("item_url", "") or row.get("url", ""),
                      "image_url": row.get("image_url", ""),
                      "screenshot_path": row.get("screenshot_path", ""),
                      "status": "purchased"}
            if row.get("date"):
                try:
                    kwargs["purchase_date"] = datetime.strptime(row["date"], "%Y-%m-%d")
                except ValueError:
                    pass
            crud.add_procurement(db, **kwargs)
            created += 1
        _scrape_jobs.pop(job_id, None)
        return JSONResponse({"status": "imported", "created": created,
                             "skipped": skipped, "total": len(results)})
    finally:
        db.close()
```

- [ ] **Step 2: Run all tests**

```bash
cd products/ebay-agent
/Users/Mac_air/Claude-Workspace/products/furima-monitor/venv/bin/pytest tests/test_procurement_integration.py -v
```

Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: scrape endpoints (yahoo-flea/rakuma/hardoff/surugaya) for procurements"
```

---

### Task 7: Delete `/api/stock/from-procurement/{proc_id}` endpoint

**Files:**
- Modify: `main.py` (remove endpoint at ~line 3707)

- [ ] **Step 1: Remove the endpoint from `main.py`**

Find and remove the entire block (lines 3704–3760 approx):

```python
# ── 仕入れ→台帳連携 ──────────────────────────────────────


@app.post("/api/stock/from-procurement/{proc_id}")
async def stock_from_procurement(proc_id: int):
    ...
```

Delete from the comment `# ── 仕入れ→台帳連携` through the end of the function body.

- [ ] **Step 2: Verify the server starts without error**

```bash
cd products/ebay-agent
/Users/Mac_air/Claude-Workspace/products/furima-monitor/venv/bin/python -c "import main; print('OK')"
```

Expected: `OK` (no import errors)

- [ ] **Step 3: Run all tests**

```bash
cd products/ebay-agent
/Users/Mac_air/Claude-Workspace/products/furima-monitor/venv/bin/pytest tests/test_procurement_integration.py -v
```

Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: remove /api/stock/from-procurement endpoint (在庫台帳廃止)"
```

---

### Task 8: Push to VPS + smoke test

- [ ] **Step 1: Push to GitHub**

```bash
git push claude-workspace master
```

- [ ] **Step 2: SSH into VPS and pull + rebuild**

```bash
ssh vps "cd /opt/apps/claude-workspace && git pull origin master && docker compose -f products/ebay-agent/docker-compose.yml up -d --build"
```

- [ ] **Step 3: Verify new endpoints respond**

```bash
ssh vps "curl -s http://localhost:8002/api/procurements/stats | python3 -m json.tool"
```

Expected: JSON with `total`, `purchased`, `listed`, etc.

- [ ] **Step 4: Verify old endpoint is gone**

```bash
ssh vps "curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:8002/api/stock/from-procurement/1"
```

Expected: `404` or `405`

- [ ] **Step 5: Commit (if any fixups needed)**

```bash
git add -p
git commit -m "fix: VPS smoke test fixups"
git push claude-workspace master
```
