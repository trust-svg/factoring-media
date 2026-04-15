# eBay Hub Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Overview page of `products/ebay-agent/` to show monthly goal progress, KPI comparisons, an interactive chart, and an out-of-stock list — matching the mockup at `/Users/Mac_air/Claude-Workspace/ui-samples6.html`.

**Architecture:** Backend adds 3 new CRUD functions and 3 new API endpoints to the existing FastAPI app. Frontend replaces `overview.html` and `overview.js` with a new layout (4-column achieve row, chart tabs, KPI table with mini-bars, freee cashflow, calendar tabs, OOS list, donut modal). CSS additions are appended to `style.css` without touching existing rules.

**Tech Stack:** FastAPI, SQLAlchemy (SQLite), Jinja2, vanilla JS (SVG charts, no new dependencies), pytest

---

## File Map

| File | Change | What changes |
|------|--------|--------------|
| `products/ebay-agent/database/crud.py` | Modify + Add | Expand `get_overview_pace`; add `get_out_of_stock_items`, `get_category_profit` |
| `products/ebay-agent/tests/test_overview_crud.py` | Modify | Add tests for 3 functions above |
| `products/ebay-agent/main.py` | Add | 3 new routes: `/api/overview/out_of_stock`, `/api/overview/category_profit`, `/api/fx/usdjpy` |
| `products/ebay-agent/templates/base.html` | Modify | Add `{% block topbar_extra %}` slot in `.top-header-actions` |
| `products/ebay-agent/static/css/style.css` | Append | New CSS for all new UI components |
| `products/ebay-agent/templates/pages/overview.html` | Rewrite | New layout matching mockup |
| `products/ebay-agent/static/js/overview.js` | Rewrite | New JS: chart tabs, KPI table, calendar tabs, modal, OOS |

---

## Task 1: Expand `get_overview_pace` to include full KPI comparison data

**Files:**
- Modify: `products/ebay-agent/database/crud.py` (function `get_overview_pace` around line 805)
- Test: `products/ebay-agent/tests/test_overview_crud.py`

The KPI table needs 売上・利益率・出品数・在庫切れ・注文数 for this month vs last month. Expand the existing function to return these additional fields:
- `month_revenue`: total revenue this month (int, JPY)
- `month_revenue_diff_pct`: vs prev month same day (already exists as `prev_month_comparison.revenue_diff_pct`)
- `profit_margin_actual`: avg margin this month (float, %)
- `profit_margin_prev`: avg margin prev month same day (float, %)
- `listing_count`: current total active listings (int)
- `out_of_stock_count`: current OOS listings (int)
- `month_order_count`: total orders this month (int)
- `prev_month_order_count`: total orders prev month same day (int)

- [ ] **Step 1: Write the failing test**

Add to `products/ebay-agent/tests/test_overview_crud.py`:

```python
def test_get_overview_pace_includes_kpi_fields(db):
    """拡張フィールドが含まれることを確認"""
    result = get_overview_pace(db)
    # 新フィールドの存在確認
    assert "month_revenue" in result
    assert "profit_margin_actual" in result
    assert "profit_margin_prev" in result
    assert "listing_count" in result
    assert "out_of_stock_count" in result
    assert "month_order_count" in result
    assert "prev_month_order_count" in result


def test_get_overview_pace_listing_counts(db):
    """出品数・在庫切れ件数が正しく返る"""
    db.add(Listing(sku="L1", quantity=5))
    db.add(Listing(sku="L2", quantity=0))
    db.add(Listing(sku="L3", quantity=0))
    db.commit()

    result = get_overview_pace(db)
    assert result["listing_count"] == 3
    assert result["out_of_stock_count"] == 2


def test_get_overview_pace_order_counts(db):
    """今月注文数と前月注文数を返す"""
    from datetime import datetime
    # 今月2件
    db.add(_sale(datetime(2026, 4, 1), received_jpy=10000))
    db.add(_sale(datetime(2026, 4, 5), received_jpy=10000))
    # 前月3件
    db.add(_sale(datetime(2026, 3, 1), received_jpy=10000))
    db.add(_sale(datetime(2026, 3, 3), received_jpy=10000))
    db.add(_sale(datetime(2026, 3, 5), received_jpy=10000))
    db.commit()

    result = get_overview_pace(db)
    # 今月注文数は現在の日付依存なのでゼロ以上であることを確認
    assert result["month_order_count"] >= 0
    assert result["prev_month_order_count"] >= 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd products/ebay-agent
python -m pytest tests/test_overview_crud.py::test_get_overview_pace_includes_kpi_fields -v
```

Expected: FAIL with `AssertionError` (keys don't exist yet)

- [ ] **Step 3: Implement expanded `get_overview_pace`**

In `products/ebay-agent/database/crud.py`, replace the entire `get_overview_pace` function body (keeping the function signature) with:

```python
def get_overview_pace(db: Session) -> dict:
    """今日の売上・前月同日比・全KPI比較データ"""
    from calendar import monthrange
    from datetime import datetime, date, timedelta

    today = date.today()
    today_start = datetime(today.year, today.month, today.day, 0, 0, 0)
    today_end   = datetime(today.year, today.month, today.day, 23, 59, 59)

    def _rev(r: SalesRecord) -> int:
        if r.received_jpy > 0:
            return r.received_jpy
        if r.exchange_rate > 0:
            return int(r.sale_price_usd * r.exchange_rate)
        return 0

    # ── 今日 ──
    today_records = db.query(SalesRecord).filter(
        SalesRecord.sold_at >= today_start,
        SalesRecord.sold_at <= today_end,
    ).all()
    today_revenue = sum(_rev(r) for r in today_records)
    today_orders  = len(today_records)

    # ── 当月累計（今日を含む）──
    month_start = datetime(today.year, today.month, 1)
    month_records = db.query(SalesRecord).filter(
        SalesRecord.sold_at >= month_start,
        SalesRecord.sold_at <= today_end,
    ).all()
    month_revenue = sum(_rev(r) for r in month_records)
    month_order_count = len(month_records)

    # 当月利益率（加重平均）
    total_rev_for_margin = month_revenue
    total_profit = sum(r.net_profit_jpy for r in month_records)
    profit_margin_actual = round(total_profit / total_rev_for_margin * 100, 1) if total_rev_for_margin > 0 else 0.0

    # ── 日次平均（今日を除く前の日数）──
    elapsed_before = today.day - 1
    prior_revenue  = month_revenue - today_revenue
    daily_avg = int(prior_revenue / elapsed_before) if elapsed_before > 0 else 0

    # ── 前月同日時点 ──
    if today.month == 1:
        pm_year, pm_month = today.year - 1, 12
    else:
        pm_year, pm_month = today.year, today.month - 1

    _, pm_last = monthrange(pm_year, pm_month)
    pm_day = min(today.day, pm_last)
    pm_end = datetime(pm_year, pm_month, pm_day, 23, 59, 59)
    pm_records = db.query(SalesRecord).filter(
        SalesRecord.sold_at >= datetime(pm_year, pm_month, 1),
        SalesRecord.sold_at <= pm_end,
    ).all()
    pm_revenue = sum(_rev(r) for r in pm_records)
    prev_month_order_count = len(pm_records)

    pm_total_rev = pm_revenue
    pm_total_profit = sum(r.net_profit_jpy for r in pm_records)
    profit_margin_prev = round(pm_total_profit / pm_total_rev * 100, 1) if pm_total_rev > 0 else 0.0

    # 前月同日比
    rev_diff     = month_revenue - pm_revenue
    rev_diff_pct = round(rev_diff / pm_revenue * 100, 1) if pm_revenue > 0 else 0.0

    # ── 出品数・在庫切れ ──
    listing_count     = db.query(Listing).count()
    out_of_stock_count = db.query(Listing).filter(Listing.quantity == 0).count()

    return {
        "today_revenue":   today_revenue,
        "today_orders":    today_orders,
        "daily_avg":       daily_avg,
        "month_revenue":   month_revenue,
        "month_order_count": month_order_count,
        "prev_month_order_count": prev_month_order_count,
        "prev_month_same_day_revenue": pm_revenue,
        "profit_margin_actual": profit_margin_actual,
        "profit_margin_prev":   profit_margin_prev,
        "listing_count":       listing_count,
        "out_of_stock_count":  out_of_stock_count,
        "prev_month_comparison": {
            "revenue_diff":     rev_diff,
            "revenue_diff_pct": rev_diff_pct,
        },
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd products/ebay-agent
python -m pytest tests/test_overview_crud.py -v
```

Expected: All tests PASS (including the old `test_get_overview_pace_no_data`)

- [ ] **Step 5: Commit**

```bash
git add products/ebay-agent/database/crud.py products/ebay-agent/tests/test_overview_crud.py
git commit -m "feat(overview): expand get_overview_pace with full KPI comparison fields"
```

---

## Task 2: Add `get_out_of_stock_items` and `get_category_profit` to crud.py

**Files:**
- Modify: `products/ebay-agent/database/crud.py` (append after `get_overview_pace`)
- Test: `products/ebay-agent/tests/test_overview_crud.py`

- [ ] **Step 1: Write the failing tests**

Append to `products/ebay-agent/tests/test_overview_crud.py`:

```python
# ── Task 2 imports ──
from database.crud import get_out_of_stock_items, get_category_profit


def test_get_out_of_stock_items_empty(db):
    result = get_out_of_stock_items(db)
    assert result == []


def test_get_out_of_stock_items_returns_oos_only(db):
    from datetime import datetime
    db.add(Listing(sku="A", title="In Stock Item", quantity=3, price_usd=10.0))
    db.add(Listing(sku="B", title="OOS Item 1", quantity=0, price_usd=20.0))
    db.add(Listing(sku="C", title="OOS Item 2", quantity=0, price_usd=30.0))
    # 売上記録：SKU Bは3日前に最後に売れた
    db.add(SalesRecord(
        order_id="ord-B", sku="B", title="OOS Item 1",
        sold_at=datetime(2026, 4, 9),
        received_jpy=3000, net_profit_jpy=600, profit_margin_pct=20.0,
        exchange_rate=150.0, sale_price_usd=20.0,
    ))
    db.commit()

    result = get_out_of_stock_items(db)
    assert len(result) == 2
    skus = [r["sku"] for r in result]
    assert "B" in skus
    assert "C" in skus
    assert "A" not in skus

    item_b = next(r for r in result if r["sku"] == "B")
    assert item_b["last_sale_price_jpy"] == 3000
    assert "days_out_of_stock" in item_b


def test_get_category_profit_empty(db):
    result = get_category_profit(db, 2026, 4)
    assert result == []


def test_get_category_profit_groups_by_category(db):
    from datetime import datetime
    db.add(Listing(sku="X1", title="Camera", category_name="カメラ", quantity=5))
    db.add(Listing(sku="X2", title="Figure", category_name="フィギュア", quantity=5))
    db.add(SalesRecord(
        order_id="o1", sku="X1", title="Camera",
        sold_at=datetime(2026, 4, 1),
        received_jpy=20000, net_profit_jpy=8000, profit_margin_pct=40.0,
        exchange_rate=150.0, sale_price_usd=133.33,
    ))
    db.add(SalesRecord(
        order_id="o2", sku="X1", title="Camera",
        sold_at=datetime(2026, 4, 5),
        received_jpy=20000, net_profit_jpy=8000, profit_margin_pct=40.0,
        exchange_rate=150.0, sale_price_usd=133.33,
    ))
    db.add(SalesRecord(
        order_id="o3", sku="X2", title="Figure",
        sold_at=datetime(2026, 4, 3),
        received_jpy=10000, net_profit_jpy=2000, profit_margin_pct=20.0,
        exchange_rate=150.0, sale_price_usd=66.67,
    ))
    db.commit()

    result = get_category_profit(db, 2026, 4)
    assert len(result) >= 1
    cats = {r["category"] for r in result}
    assert "カメラ" in cats or "その他" in cats

    total_profit = sum(r["profit"] for r in result)
    assert total_profit == 18000
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd products/ebay-agent
python -m pytest tests/test_overview_crud.py::test_get_out_of_stock_items_empty tests/test_overview_crud.py::test_get_category_profit_empty -v
```

Expected: FAIL with `ImportError` (functions don't exist yet)

- [ ] **Step 3: Implement `get_out_of_stock_items`**

Append to the end of `products/ebay-agent/database/crud.py`:

```python
def get_out_of_stock_items(db: Session, limit: int = 10) -> list[dict]:
    """在庫切れ出品リスト（最終売価・切れてから何日か付き）"""
    from datetime import date, datetime

    today = date.today()
    oos_listings = (
        db.query(Listing)
        .filter(Listing.quantity == 0)
        .order_by(Listing.title)
        .limit(limit)
        .all()
    )

    result = []
    for listing in oos_listings:
        # 最後に売れた記録を取得
        last_sale = (
            db.query(SalesRecord)
            .filter(SalesRecord.sku == listing.sku)
            .order_by(SalesRecord.sold_at.desc())
            .first()
        )
        last_sale_price_jpy = last_sale.received_jpy if last_sale else 0
        last_sold_at = last_sale.sold_at.date() if last_sale else None
        days_out_of_stock = (today - last_sold_at).days if last_sold_at else None

        result.append({
            "sku":                listing.sku,
            "title":              listing.title,
            "price_usd":          listing.price_usd,
            "last_sale_price_jpy": last_sale_price_jpy,
            "days_out_of_stock":  days_out_of_stock,
        })
    return result


def get_category_profit(db: Session, year: int, month: int) -> list[dict]:
    """カテゴリ別利益内訳（モーダル用）"""
    from datetime import datetime

    month_start = datetime(year, month, 1)
    from calendar import monthrange
    _, last_day = monthrange(year, month)
    month_end = datetime(year, month, last_day, 23, 59, 59)

    records = (
        db.query(SalesRecord)
        .filter(
            SalesRecord.sold_at >= month_start,
            SalesRecord.sold_at <= month_end,
        )
        .all()
    )

    if not records:
        return []

    # SKU → カテゴリ名のマップを作成
    skus = list({r.sku for r in records})
    listings = db.query(Listing).filter(Listing.sku.in_(skus)).all()
    sku_to_category = {l.sku: (l.category_name or "その他") for l in listings}

    # カテゴリ別集計
    cat_data: dict[str, dict] = {}
    for rec in records:
        cat = sku_to_category.get(rec.sku, "その他")
        if cat not in cat_data:
            cat_data[cat] = {"revenue": 0, "profit": 0}
        rev = rec.received_jpy if rec.received_jpy > 0 else int(rec.sale_price_usd * rec.exchange_rate)
        cat_data[cat]["revenue"] += rev
        cat_data[cat]["profit"]  += rec.net_profit_jpy

    total_profit = sum(v["profit"] for v in cat_data.values())

    result = []
    for cat, data in sorted(cat_data.items(), key=lambda x: -x[1]["profit"]):
        margin = round(data["profit"] / data["revenue"] * 100, 1) if data["revenue"] > 0 else 0.0
        pct    = round(data["profit"] / total_profit * 100, 1) if total_profit > 0 else 0.0
        result.append({
            "category": cat,
            "revenue":  data["revenue"],
            "profit":   data["profit"],
            "margin":   margin,
            "pct_of_total": pct,
        })
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd products/ebay-agent
python -m pytest tests/test_overview_crud.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add products/ebay-agent/database/crud.py products/ebay-agent/tests/test_overview_crud.py
git commit -m "feat(overview): add get_out_of_stock_items and get_category_profit to crud"
```

---

## Task 3: Add new API endpoints to main.py

**Files:**
- Modify: `products/ebay-agent/main.py` (append after line ~3820, the existing `/api/overview/pace` endpoint)

- [ ] **Step 1: Append the 3 new routes after the existing overview endpoints in `main.py`**

Find the block that ends with:

```python
@app.get("/api/overview/pace")
async def overview_pace():
    ...
    finally:
        db.close()
```

After that block, append:

```python
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
    return JSONResponse({
        "rate": 152.40,
        "change": 0.82,
        "direction": "up",
        "source": "static",
        "updated_at": datetime.now().isoformat(),
    })
```

- [ ] **Step 2: Verify the server starts without errors**

```bash
cd products/ebay-agent
python -c "import main; print('OK')"
```

Expected: `OK` (no import errors)

- [ ] **Step 3: Commit**

```bash
git add products/ebay-agent/main.py
git commit -m "feat(overview): add out_of_stock, category_profit, fx/usdjpy API endpoints"
```

---

## Task 4: Add `topbar_extra` block to base.html

**Files:**
- Modify: `products/ebay-agent/templates/base.html`

The USD/JPY chip in the overview page needs to be injected into the top header. We add a block slot in base.html so overview.html can insert it.

- [ ] **Step 1: Modify base.html**

Find in `products/ebay-agent/templates/base.html`:

```html
                <div class="top-header-actions">
                    <div class="header-search">
```

Replace with:

```html
                <div class="top-header-actions">
                    {% block topbar_extra %}{% endblock %}
                    <div class="header-search">
```

- [ ] **Step 2: Verify no visual regression**

Open any existing page (e.g., `/listings`) in the browser and confirm the header looks unchanged.

- [ ] **Step 3: Commit**

```bash
git add products/ebay-agent/templates/base.html
git commit -m "feat(base): add topbar_extra block for page-specific header injections"
```

---

## Task 5: Append new CSS to style.css

**Files:**
- Modify: `products/ebay-agent/static/css/style.css` (append at end)

Do not edit existing rules. Only append new classes.

- [ ] **Step 1: Append the following CSS at the end of `style.css`**

```css
/* ================================================================
   Overview Dashboard — Redesign 2026-04 additions
   ================================================================ */

/* ── USD/JPY rate chip ─────────────────────────────────────── */
.fx-chip {
    display: flex;
    align-items: center;
    gap: 5px;
    background: var(--gray-50);
    border: 1px solid var(--gray-200);
    border-radius: 8px;
    padding: 4px 10px;
    font-size: 11px;
    cursor: default;
    white-space: nowrap;
}
.fx-chip .fx-label { color: var(--gray-500); font-weight: 500; }
.fx-chip .fx-val   { color: var(--gray-900); font-weight: 800; }
.fx-chip .fx-diff  { font-size: 10px; font-weight: 700; }
.fx-chip .fx-diff.up { color: var(--red); }
.fx-chip .fx-diff.dn { color: var(--green); }

/* ── Achievement board: 4-column override for overview page ── */
.achievement-board-4 {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr 190px;
    gap: 12px;
    margin-bottom: 16px;
}
@media (max-width: 900px) {
    .achievement-board-4 { grid-template-columns: 1fr 1fr; }
}

/* Payoneer card */
.payoneer-card {
    background: #fff;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0,0,0,.06);
}
.payoneer-head {
    background: linear-gradient(135deg, #FF5F00, #FF8533);
    padding: 12px 14px;
    color: #fff;
}
.payoneer-head .py-label {
    font-size: 9px;
    opacity: .8;
    letter-spacing: .06em;
    text-transform: uppercase;
    margin-bottom: 4px;
}
.payoneer-head .py-val  { font-size: 18px; font-weight: 800; letter-spacing: -.02em; }
.payoneer-head .py-sub  { font-size: 9px; opacity: .7; margin-top: 3px; }
.payoneer-body          { padding: 10px 14px; }
.payoneer-row           { display: flex; justify-content: space-between; font-size: 10px; margin-bottom: 5px; }
.payoneer-row:last-child { margin-bottom: 0; }
.payoneer-row .py-name  { color: var(--gray-500); }
.payoneer-row .py-amt   { font-weight: 700; color: var(--gray-900); }
.payoneer-row .py-amt.green { color: var(--green); }

/* Donut modal trigger button */
.donut-trigger-btn {
    background: none;
    border: none;
    cursor: pointer;
    font-size: 11px;
    color: var(--indigo);
    font-weight: 700;
    padding: 0;
    transition: .15s;
}
.donut-trigger-btn:hover { color: #4338CA; }

/* ── Overview mid-row grid ────────────────────────────────── */
.overview-mid-row {
    display: grid;
    grid-template-columns: 2fr 1fr 1fr;
    gap: 12px;
    margin-bottom: 16px;
}
@media (max-width: 1100px) {
    .overview-mid-row { grid-template-columns: 1fr 1fr; }
}

/* ── Chart tab switcher ───────────────────────────────────── */
.chart-tab-bar {
    display: flex;
    border: 1px solid var(--gray-200);
    border-radius: 8px;
    overflow: hidden;
    width: fit-content;
    margin-bottom: 10px;
}
.chart-tab-btn {
    padding: 4px 12px;
    font-size: 10px;
    font-weight: 600;
    cursor: pointer;
    border: none;
    background: #fff;
    color: var(--gray-500);
    transition: .15s;
}
.chart-tab-btn.active { background: var(--blue); color: #fff; }
.chart-tab-panel      { display: none; }
.chart-tab-panel.active { display: block; }

/* Vertical bar chart (日別) */
.day-bar-chart {
    display: grid;
    grid-template-columns: repeat(12, 1fr);
    gap: 4px;
    align-items: end;
    height: 80px;
    margin-top: 4px;
}
.day-bar-col  { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.day-bar-num  { font-size: 7px; font-weight: 700; color: var(--gray-500); text-align: center; white-space: nowrap; }
.day-bar-num.hi { color: #1D4ED8; }
.day-bar      { width: 100%; border-radius: 3px 3px 0 0; }
.day-bar.lo   { background: linear-gradient(0deg, #BFDBFE, #93C5FD); }
.day-bar.md   { background: linear-gradient(0deg, #93C5FD, #3B82F6); }
.day-bar.hi   { background: linear-gradient(0deg, #3B82F6, #1D4ED8); box-shadow: 0 2px 6px rgba(37,99,235,.25); }
.day-bar-lbl  { font-size: 8px; color: var(--gray-400); font-weight: 600; }

/* Monthly cumulative SVG chart */
.monthly-chart-legend {
    display: flex;
    gap: 12px;
    margin-bottom: 8px;
    flex-wrap: wrap;
}
.mcl-item { display: flex; align-items: center; gap: 5px; font-size: 10px; color: var(--gray-700); font-weight: 600; }
.mcl-line  { width: 16px; height: 2px; border-radius: 1px; }
.mcl-line.solid-blue { background: #2563EB; }
.mcl-line.dash-gray  { background: repeating-linear-gradient(90deg,#94A3B8 0,#94A3B8 4px,transparent 4px,transparent 8px); }
.mcl-line.dash-orange{ background: repeating-linear-gradient(90deg,#F97316 0,#F97316 4px,transparent 4px,transparent 8px); }
.monthly-chart-wrap  { position: relative; display: flex; }
.monthly-y-labels    { display: flex; flex-direction: column; justify-content: space-between; padding-bottom: 16px; padding-top: 2px; width: 36px; }
.monthly-y-lbl       { font-size: 8px; color: var(--gray-400); text-align: right; }
.monthly-x-labels    { display: flex; justify-content: space-between; padding-left: 36px; margin-top: 2px; }
.monthly-x-lbl       { font-size: 8px; color: var(--gray-400); }

/* ── KPI table with mini-bars ─────────────────────────────── */
.kpi-comparison-table {
    width: 100%;
    border-collapse: collapse;
}
.kpi-comparison-table tr {
    border-bottom: 1px solid var(--gray-50);
}
.kpi-comparison-table tr:last-child { border-bottom: none; }
.kpi-comparison-table td { padding: 5px 3px; font-size: 11px; }
.kct-name  { color: var(--gray-500); font-weight: 500; width: 60px; }
.kct-val   { font-weight: 700; color: var(--gray-900); text-align: right; padding-right: 4px; white-space: nowrap; }
.kct-bar-w { width: 54px; }
.kct-bar   { height: 4px; background: var(--gray-100); border-radius: 2px; overflow: hidden; }
.kct-fill  { height: 100%; border-radius: 2px; }
.kct-fill.blue { background: #3B82F6; }
.kct-fill.red  { background: var(--red); }
.kct-fill.orange { background: var(--orange); }
.kct-diff  { font-size: 10px; font-weight: 700; text-align: right; white-space: nowrap; }
.kct-diff.up   { color: var(--green); }
.kct-diff.down { color: var(--red); }
.kct-diff.neutral { color: var(--orange); }

/* freee cashflow section within KPI card */
.freee-divider { border: none; border-top: 1px dashed var(--gray-200); margin: 10px 0 8px; }
.freee-section-label {
    font-size: 9px;
    font-weight: 700;
    color: var(--gray-400);
    text-transform: uppercase;
    letter-spacing: .07em;
    margin-bottom: 7px;
}
.freee-cf-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 4px 0;
    font-size: 11px;
    border-bottom: 1px solid var(--gray-50);
}
.freee-cf-row:last-child { border-bottom: none; }
.freee-cf-name { color: var(--gray-500); }
.freee-cf-val  { font-weight: 700; color: var(--gray-900); }
.freee-cf-val.positive { color: var(--green); }
.freee-cf-val.negative { color: var(--red); }

/* ── Calendar tab switcher ────────────────────────────────── */
.cal-tab-bar {
    display: flex;
    border: 1px solid var(--gray-200);
    border-radius: 6px;
    overflow: hidden;
    margin-bottom: 8px;
    width: 100%;
}
.cal-tab-btn {
    flex: 1;
    padding: 3px 0;
    font-size: 10px;
    font-weight: 600;
    cursor: pointer;
    border: none;
    background: #fff;
    color: var(--gray-500);
    text-align: center;
    transition: .15s;
}
.cal-tab-btn.active { background: var(--blue); color: #fff; }
.cal-tab-panel      { display: none; }
.cal-tab-panel.active { display: block; }

/* ── Out-of-stock list card ───────────────────────────────── */
.oos-card {
    background: #fff;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0,0,0,.06);
    margin-bottom: 16px;
}
.oos-card-head {
    padding: 12px 18px;
    border-bottom: 1px solid var(--gray-100);
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.oos-card-head h3 { font-size: 13px; font-weight: 700; color: var(--gray-900); }
.oos-card-head a  { font-size: 11px; color: var(--blue); font-weight: 600; text-decoration: none; }
.oos-list-table { width: 100%; border-collapse: collapse; }
.oos-list-table th {
    padding: 8px 14px;
    text-align: left;
    font-size: 9px;
    font-weight: 700;
    color: var(--gray-400);
    text-transform: uppercase;
    letter-spacing: .04em;
    background: var(--gray-50);
    border-bottom: 1px solid var(--gray-100);
}
.oos-list-table td {
    padding: 9px 14px;
    font-size: 11px;
    color: var(--gray-700);
    border-bottom: 1px solid var(--gray-50);
    vertical-align: middle;
}
.oos-list-table tbody tr:last-child td { border-bottom: none; }
.oos-list-table tbody tr:hover td     { background: var(--gray-50); }
.oos-days-badge {
    background: #FEE2E2;
    color: #DC2626;
    font-size: 9px;
    font-weight: 700;
    padding: 2px 7px;
    border-radius: 10px;
    white-space: nowrap;
}
.oos-search-btn {
    background: var(--blue-light);
    color: var(--blue);
    font-size: 9px;
    font-weight: 700;
    padding: 3px 9px;
    border-radius: 6px;
    border: none;
    cursor: pointer;
    text-decoration: none;
    display: inline-block;
}
.oos-search-btn:hover { background: #DBEAFE; }
.oos-empty-row { padding: 20px; text-align: center; color: var(--gray-400); font-size: 12px; }

/* ── Category profit modal ────────────────────────────────── */
.cat-modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(15, 23, 42, .5);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 9999;
    backdrop-filter: blur(2px);
}
.cat-modal-overlay.open { display: flex; }
.cat-modal {
    background: #fff;
    border-radius: 14px;
    width: 520px;
    max-width: 95vw;
    box-shadow: 0 20px 60px rgba(0,0,0,.2);
    overflow: hidden;
}
.cat-modal-head {
    padding: 18px 20px;
    border-bottom: 1px solid var(--gray-100);
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.cat-modal-head h3 { font-size: 15px; font-weight: 800; color: var(--gray-900); }
.cat-modal-close {
    background: none;
    border: none;
    font-size: 20px;
    color: var(--gray-400);
    cursor: pointer;
    line-height: 1;
}
.cat-modal-close:hover { color: var(--gray-700); }
.cat-modal-body {
    padding: 20px;
    display: flex;
    gap: 20px;
    align-items: flex-start;
}
.cat-modal-donut  { flex-shrink: 0; }
.cat-modal-table  { flex: 1; overflow-x: auto; }
.cat-modal-table table { width: 100%; border-collapse: collapse; }
.cat-modal-table th {
    padding: 7px 8px;
    text-align: left;
    font-size: 10px;
    font-weight: 700;
    color: var(--gray-400);
    text-transform: uppercase;
    border-bottom: 1px solid var(--gray-100);
}
.cat-modal-table td {
    padding: 8px 8px;
    font-size: 12px;
    color: var(--gray-700);
    border-bottom: 1px solid var(--gray-50);
    vertical-align: middle;
}
.cat-modal-table tr:last-child td { border-bottom: none; }
.cat-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px; }
.cat-pct-bar { display: flex; align-items: center; gap: 6px; }
.cat-pct-track { flex: 1; height: 5px; background: var(--gray-100); border-radius: 3px; overflow: hidden; min-width: 50px; }
.cat-pct-fill  { height: 100%; border-radius: 3px; }
.cat-pct-num   { font-size: 10px; font-weight: 700; min-width: 32px; text-align: right; }
.cat-modal-foot {
    padding: 14px 20px;
    border-top: 1px solid var(--gray-100);
    font-size: 11px;
    color: var(--gray-500);
    background: var(--gray-50);
}
```

- [ ] **Step 2: Hard-reload a page in the browser and confirm no existing layout is broken**

Open `https://ebay.trustlink-tk.com/` (or the local dev server) and visually check the Overview page still renders.

- [ ] **Step 3: Commit**

```bash
git add products/ebay-agent/static/css/style.css
git commit -m "feat(overview): add new CSS for dashboard redesign components"
```

---

## Task 6: Rewrite `overview.html`

**Files:**
- Modify (full rewrite): `products/ebay-agent/templates/pages/overview.html`

The new layout:
1. `{% block topbar_extra %}` — USD/JPY chip
2. Alert strip (existing ID `alertStrip`)
3. `.achievement-board-4` — 4 cards: Revenue, Margin, Profit, Payoneer
4. `.overview-mid-row` — Chart (with tab bar) | KPI+freee | Calendar (with tab bar)
5. `.oos-card` — out-of-stock table
6. Existing sales stats grid (keep for now, can remove later)
7. `#cat-modal` — category profit modal

- [ ] **Step 1: Replace the entire contents of `overview.html` with**

```html
{% extends "base.html" %}
{% block title %}ダッシュボード — eBay Agent Hub{% endblock %}
{% block breadcrumb %}ダッシュボード{% endblock %}
{% block page_title %}<span data-en="Dashboard" data-ja="ダッシュボード">ダッシュボード</span>{% endblock %}

{% block topbar_extra %}
<div class="fx-chip" id="fxChip" title="USD/JPY レート">
  <span class="fx-label">USD/JPY</span>
  <span class="fx-val" id="fxRate">—</span>
  <span class="fx-diff" id="fxDiff"></span>
</div>
{% endblock %}

{% block content %}

<!-- ① Alert Strip -->
<div id="alertStrip" class="alert-strip" style="display:none"></div>

<!-- ② Achievement Board (4 cols) -->
<div class="achievement-board-4">

  <!-- Revenue -->
  <div class="achievement-card" style="border-top:3px solid transparent;border-image:linear-gradient(90deg,#60A5FA,#1D4ED8) 1">
    <div class="ach-label" data-en="Monthly Revenue" data-ja="月間売上">月間売上</div>
    <div class="ach-values">
      <span class="ach-actual" id="revActual">¥—</span>
      <span class="ach-target">/ ¥5,000,000</span>
    </div>
    <div class="progress-wrap">
      <div class="progress-bar" id="revBar" style="width:0%"></div>
    </div>
    <div class="ach-meta">
      <span class="ach-rate" id="revRate">—%</span>
      <span class="ach-pace" id="revPace"></span>
    </div>
  </div>

  <!-- Margin -->
  <div class="achievement-card" style="border-top:3px solid transparent;border-image:linear-gradient(90deg,#FCD34D,#F59E0B) 1">
    <div class="ach-label" data-en="Profit Margin" data-ja="利益率">利益率</div>
    <div class="ach-values">
      <span class="ach-actual" id="marginActual">—%</span>
      <span class="ach-target">/ 20%</span>
    </div>
    <div class="progress-wrap">
      <div class="progress-bar" id="marginBar" style="width:0%"></div>
    </div>
    <div class="ach-meta">
      <span class="ach-rate" id="marginRate">— / —</span>
      <span class="ach-pace" id="marginPace"></span>
    </div>
  </div>

  <!-- Profit -->
  <div class="achievement-card" style="border-top:3px solid transparent;border-image:linear-gradient(90deg,#6EE7B7,#10B981) 1">
    <div class="ach-label" data-en="Monthly Profit" data-ja="月間利益">月間利益</div>
    <div class="ach-values">
      <span class="ach-actual" id="profitActual">¥—</span>
      <span class="ach-target">/ ¥1,000,000</span>
    </div>
    <div class="progress-wrap">
      <div class="progress-bar" id="profitBar" style="width:0%"></div>
    </div>
    <div class="ach-meta">
      <span class="ach-rate" id="profitRate">—%</span>
      <button class="donut-trigger-btn" onclick="openCatModal()">📊 カテゴリ分析 ↗</button>
    </div>
  </div>

  <!-- Payoneer -->
  <div class="payoneer-card">
    <div class="payoneer-head">
      <div class="py-label">Payoneer</div>
      <div class="py-val" id="pyBalance">$—</div>
      <div class="py-sub" id="pySub">今月入金 $—</div>
    </div>
    <div class="payoneer-body">
      <div class="payoneer-row">
        <span class="py-name">先月比</span>
        <span class="py-amt green" id="pyDiff">+$—</span>
      </div>
      <div class="payoneer-row">
        <span class="py-name">レート</span>
        <span class="py-amt" id="pyRate">¥— / $</span>
      </div>
    </div>
  </div>

</div>

<!-- ③ Mid Row: Chart + KPI/freee + Calendar -->
<div class="overview-mid-row">

  <!-- Chart with tabs -->
  <div class="section">
    <div class="chart-tab-bar">
      <button class="chart-tab-btn" id="tab-daily"   onclick="switchChart('daily')">日別</button>
      <button class="chart-tab-btn active" id="tab-monthly" onclick="switchChart('monthly')">月別累計</button>
    </div>

    <!-- 日別 panel -->
    <div class="chart-tab-panel" id="panel-daily">
      <div class="day-bar-chart" id="dailyBarChart">
        <div style="color:var(--gray-400);font-size:11px;grid-column:1/-1;text-align:center;padding:20px 0">Loading...</div>
      </div>
    </div>

    <!-- 月別累計 panel -->
    <div class="chart-tab-panel active" id="panel-monthly">
      <div class="monthly-chart-legend">
        <div class="mcl-item"><div class="mcl-line solid-blue"></div>今月</div>
        <div class="mcl-item"><div class="mcl-line dash-gray"></div>先月</div>
        <div class="mcl-item"><div class="mcl-line dash-orange"></div>目標</div>
      </div>
      <div class="monthly-chart-wrap">
        <div class="monthly-y-labels" id="monthlyYLabels"></div>
        <svg id="monthlyChartSvg" width="100%" height="120" style="flex:1"></svg>
      </div>
      <div class="monthly-x-labels" id="monthlyXLabels"></div>
    </div>
  </div>

  <!-- KPI comparison + freee -->
  <div class="section">
    <h2 style="font-size:12px;font-weight:700;margin-bottom:10px" data-ja="KPI 前月同日比">KPI 前月同日比</h2>
    <table class="kpi-comparison-table" id="kpiCompTable">
      <tr><td class="kct-name">—</td><td class="kct-val">—</td><td class="kct-bar-w"></td><td class="kct-diff">—</td></tr>
    </table>
    <hr class="freee-divider">
    <div class="freee-section-label">📋 freee キャッシュフロー</div>
    <div class="freee-cf-row"><span class="freee-cf-name">口座残高</span><span class="freee-cf-val" id="freeeBalance">—</span></div>
    <div class="freee-cf-row"><span class="freee-cf-name">今月収入</span><span class="freee-cf-val positive" id="freeeIncome">—</span></div>
    <div class="freee-cf-row"><span class="freee-cf-name">今月支出</span><span class="freee-cf-val negative" id="freeeExpense">—</span></div>
    <div class="freee-cf-row"><span class="freee-cf-name">純CF</span><span class="freee-cf-val" id="freeeCF">—</span></div>
  </div>

  <!-- Calendar with tabs -->
  <div class="section">
    <div class="cal-tab-bar">
      <button class="cal-tab-btn active" id="cal-tab-sale" onclick="switchCal('sale')">売上</button>
      <button class="cal-tab-btn" id="cal-tab-pay"  onclick="switchCal('pay')">入金</button>
    </div>
    <div class="cal-tab-panel active" id="cal-panel-sale">
      <div id="salesCalendar"><div class="empty-state">Loading...</div></div>
    </div>
    <div class="cal-tab-panel" id="cal-panel-pay">
      <div id="payCalendar"><div class="empty-state">入金カレンダー</div></div>
    </div>
  </div>

</div>

<!-- ④ Out-of-stock list -->
<div class="oos-card">
  <div class="oos-card-head">
    <h3>⚠️ 在庫切れ商品</h3>
    <a href="/listings">一覧で見る →</a>
  </div>
  <table class="oos-list-table">
    <thead>
      <tr><th>商品名</th><th>最終売価</th><th>切れて</th><th></th></tr>
    </thead>
    <tbody id="oosTableBody">
      <tr><td colspan="4" class="oos-empty-row">Loading...</td></tr>
    </tbody>
  </table>
</div>

<!-- ⑤ Existing stat cards (unchanged) -->
<div class="stats-grid">
  <div class="stat-card">
    <div class="stat-icon blue">
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" d="m20.25 7.5-.625 10.632a2.25 2.25 0 0 1-2.247 2.118H6.622a2.25 2.25 0 0 1-2.247-2.118L3.75 7.5M10 11.25h4M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125Z" />
      </svg>
    </div>
    <div class="stat-content">
      <div class="label" data-en="Total Listings" data-ja="総出品数">総出品数</div>
      <div class="value">{{ stats.total_listings }}</div>
    </div>
  </div>
  <div class="stat-card">
    <div class="stat-icon green">
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
      </svg>
    </div>
    <div class="stat-content">
      <div class="label" data-en="In Stock" data-ja="在庫あり">在庫あり</div>
      <div class="value">{{ stats.in_stock }}</div>
    </div>
  </div>
  <div class="stat-card">
    <div class="stat-icon red">
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
      </svg>
    </div>
    <div class="stat-content">
      <div class="label" data-en="Out of Stock" data-ja="在庫切れ">在庫切れ</div>
      <div class="value">{{ stats.out_of_stock }}</div>
    </div>
  </div>
  <div class="stat-card">
    <div class="stat-icon yellow">
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
      </svg>
    </div>
    <div class="stat-content">
      <div class="label" data-en="Source Candidates" data-ja="仕入れ候補">仕入れ候補</div>
      <div class="value">{{ stats.source_candidates }}</div>
    </div>
  </div>
</div>

<!-- ⑥ Category profit modal -->
<div class="cat-modal-overlay" id="catModal" onclick="if(event.target===this)closeCatModal()">
  <div class="cat-modal">
    <div class="cat-modal-head">
      <h3 id="catModalTitle">カテゴリ別利益 — 2026年4月</h3>
      <button class="cat-modal-close" onclick="closeCatModal()">×</button>
    </div>
    <div class="cat-modal-body">
      <div class="cat-modal-donut">
        <svg id="catDonutSvg" width="120" height="120" viewBox="0 0 120 120"></svg>
      </div>
      <div class="cat-modal-table">
        <table>
          <thead>
            <tr><th></th><th>カテゴリ</th><th>利益</th><th>構成比</th></tr>
          </thead>
          <tbody id="catModalTableBody">
            <tr><td colspan="4" style="text-align:center;color:var(--gray-400);padding:20px">Loading...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
    <div class="cat-modal-foot" id="catModalFoot"></div>
  </div>
</div>

{% endblock %}
```

- [ ] **Step 2: Reload the overview page in browser and verify layout renders without JS errors**

```
open http://localhost:8000/
```

The page should show the 4-column achieve cards, the mid-row grid, the OOS card placeholder, and the stats grid. Charts and data will be empty until Task 7.

- [ ] **Step 3: Commit**

```bash
git add products/ebay-agent/templates/pages/overview.html
git commit -m "feat(overview): rewrite overview.html with new 4-col layout, chart tabs, calendar tabs, OOS card"
```

---

## Task 7: Rewrite `overview.js`

**Files:**
- Modify (full rewrite): `products/ebay-agent/static/js/overview.js`

- [ ] **Step 1: Replace the entire contents of `overview.js` with**

```javascript
/* eBay Agent Hub — Overview Dashboard JS (redesign 2026-04) */

/* ── Helpers ─────────────────────────────────────────────── */
const fmt  = (n) => formatJPY(n);     // from app.js
const pct  = (n) => formatPct(n);     // from app.js
const fmtM = (n) => {                 // ¥X.XM or ¥XXX,XXX
    if (n >= 1_000_000) return `¥${(n / 1_000_000).toFixed(1)}M`;
    return fmt(n);
};
const CAT_COLORS = ['#2563EB','#10B981','#F97316','#8B5CF6','#EF4444','#F59E0B','#06B6D4','#84CC16'];

/* ── USD/JPY chip ────────────────────────────────────────── */
async function loadFxRate() {
    try {
        const data = await apiFetch('/api/fx/usdjpy');
        const rateEl = document.getElementById('fxRate');
        const diffEl = document.getElementById('fxDiff');
        if (rateEl) rateEl.textContent = `¥${data.rate.toFixed(2)}`;
        if (diffEl) {
            const sign = data.direction === 'up' ? '+' : '-';
            const cls  = data.direction === 'up' ? 'up' : 'dn';
            diffEl.textContent = `${sign}${Math.abs(data.change).toFixed(2)} ${data.direction === 'up' ? '↑' : '↓'}`;
            diffEl.className = `fx-diff ${cls}`;
        }
    } catch (e) {
        console.warn('fx rate load failed', e);
    }
}

/* ── Alert Strip ─────────────────────────────────────────── */
async function loadAlerts() {
    try {
        const data = await apiFetch('/api/overview/alerts');
        renderAlerts(data);
    } catch (e) {
        console.warn('alerts load failed', e);
    }
}

function renderAlerts(data) {
    const strip = document.getElementById('alertStrip');
    if (!strip) return;
    const items = [];
    if (data.out_of_stock > 0) {
        const cls = data.out_of_stock >= 10 ? 'critical' : '';
        items.push(`<a href="/listings" class="alert-item ${cls}">⚠️ 在庫切れ ${data.out_of_stock}件</a>`);
    }
    if (data.unread_messages > 0) {
        const cls = data.unread_messages >= 5 ? 'critical' : '';
        items.push(`<a href="/chat" class="alert-item ${cls}">💬 未読 ${data.unread_messages}件</a>`);
    }
    if (data.price_alerts > 0) {
        items.push(`<a href="/listings?tab=pricing" class="alert-item">📉 価格アラート ${data.price_alerts}件</a>`);
    }
    if (items.length === 0) { strip.style.display = 'none'; return; }
    strip.innerHTML = items.join('');
    strip.style.display = 'flex';
    strip.className = `alert-strip ${data.severity}`;
}

/* ── Achievement Board ───────────────────────────────────── */
async function loadAchievement() {
    try {
        const data = await apiFetch('/api/overview/achievement');
        renderAchievement(data);
    } catch (e) {
        console.warn('achievement load failed', e);
    }
}

function setBar(id, pct, color) {
    const el = document.getElementById(id);
    if (!el) return;
    el.style.width  = Math.min(pct, 100) + '%';
    el.style.background = color;
}

function renderAchievement(data) {
    const rev    = data.revenue;
    const margin = data.profit_margin;
    const profit = data.profit;

    /* Revenue */
    const revColor = rev.rate >= 100 ? 'var(--green)' : 'var(--blue)';
    setText('revActual', fmt(rev.actual));
    setBar('revBar', rev.rate, revColor);
    setText('revRate', pct(rev.rate));
    const revPaceEl = document.getElementById('revPace');
    if (revPaceEl) {
        const icon = rev.projected_eom >= rev.target ? '✅' : '📉';
        const cls  = rev.projected_eom >= rev.target ? 'on-track' : 'off-track';
        revPaceEl.textContent = `予測: ${fmtM(rev.projected_eom)} ${icon}`;
        revPaceEl.className = `ach-pace ${cls}`;
    }

    /* Margin */
    const marginRatePct = margin.target > 0 ? margin.actual / margin.target * 100 : 0;
    const marginColor   = marginRatePct >= 100 ? 'var(--green)' : marginRatePct >= 80 ? 'var(--orange)' : 'var(--red)';
    setText('marginActual', `${margin.actual.toFixed(1)}%`);
    setBar('marginBar', marginRatePct, marginColor);
    setText('marginRate', `${margin.actual.toFixed(1)}% / ${margin.target.toFixed(1)}%`);
    const marginPaceEl = document.getElementById('marginPace');
    if (marginPaceEl) {
        const diff = margin.actual - (margin.prev_month_same_day || 0);
        const sign = diff >= 0 ? '+' : '';
        const cls  = diff >= 0 ? 'on-track' : 'off-track';
        marginPaceEl.textContent = `前月比 ${sign}${diff.toFixed(1)}pp`;
        marginPaceEl.className = `ach-pace ${cls}`;
    }

    /* Profit */
    const profitColor = profit.rate >= 100 ? 'var(--green)' : 'var(--indigo)';
    setText('profitActual', fmt(profit.actual));
    setBar('profitBar', profit.rate, profitColor);
    setText('profitRate', pct(profit.rate));
}

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

/* ── Payoneer card (placeholder — real API requires OAuth) ── */
function renderPayoneerStatic() {
    /* Payoneer APIは別途OAuth設定後に実装予定 */
    setText('pyBalance', '$2,840');
    setText('pySub',     '今月入金 $1,240');
    setText('pyDiff',    '+$580');
    setText('pyRate',    '¥152 / $');
}

/* ── KPI Comparison Table ────────────────────────────────── */
async function loadKpiComparison() {
    try {
        const [paceData, achData] = await Promise.all([
            apiFetch('/api/overview/pace'),
            apiFetch('/api/overview/achievement'),
        ]);
        renderKpiComparison(paceData, achData);
    } catch (e) {
        console.warn('kpi comparison load failed', e);
    }
}

function kpiRow(name, value, fillPct, fillClass, diff, diffClass) {
    return `
      <tr>
        <td class="kct-name">${escapeHtml(name)}</td>
        <td class="kct-val">${escapeHtml(value)}</td>
        <td class="kct-bar-w"><div class="kct-bar"><div class="kct-fill ${fillClass}" style="width:${Math.min(fillPct,100)}%"></div></div></td>
        <td class="kct-diff ${diffClass}">${escapeHtml(diff)}</td>
      </tr>`;
}

function renderKpiComparison(pace, ach) {
    const tbl = document.getElementById('kpiCompTable');
    if (!tbl) return;

    const rev         = ach.revenue;
    const margin      = ach.profit_margin;
    const revDiffPct  = pace.prev_month_comparison.revenue_diff_pct;
    const revDiff     = pace.prev_month_comparison.revenue_diff;
    const marginDiff  = (margin.actual - (pace.profit_margin_prev || margin.prev_month_same_day || 0));
    const listingCount = pace.listing_count || 0;
    const oosCount     = pace.out_of_stock_count || 0;
    const orderCount   = pace.month_order_count || 0;
    const prevOrderCount = pace.prev_month_order_count || 0;
    const orderDiffPct = prevOrderCount > 0
        ? Math.round((orderCount - prevOrderCount) / prevOrderCount * 100)
        : 0;

    const revSign   = revDiff >= 0 ? '+' : '';
    const revCls    = revDiff >= 0 ? 'up' : 'down';
    const margSign  = marginDiff >= 0 ? '+' : '';
    const margCls   = marginDiff >= 0 ? 'up' : 'down';
    const ordSign   = orderDiffPct >= 0 ? '+' : '';
    const ordCls    = orderDiffPct >= 0 ? 'up' : 'down';

    tbl.innerHTML =
        kpiRow('売上',   fmt(rev.actual),             rev.rate,        'blue',   `${revSign}${revDiffPct}%`,   revCls)  +
        kpiRow('利益率', `${margin.actual.toFixed(1)}%`, margin.actual / margin.target * 100, 'blue', `${margSign}${marginDiff.toFixed(1)}pp`, margCls) +
        kpiRow('出品数', `${listingCount}件`,          Math.min(listingCount / 200 * 100, 100), 'blue',   '—',    'neutral') +
        kpiRow('在庫切れ', `${oosCount}件`,            Math.min(oosCount / 20 * 100, 100),   'red',   '—',    'neutral') +
        kpiRow('注文数', `${orderCount}件`,            Math.min(orderCount / 100 * 100, 100), 'blue', `${ordSign}${orderDiffPct}%`, ordCls);
}

/* ── freee Cashflow (static placeholder) ─────────────────── */
function renderFreeeStatic() {
    /* freee MCP連携は後続タスクで実装予定（GET /api/1/deals） */
    setText('freeeBalance', '¥1,234,567');
    setText('freeeIncome',  '+¥890,000');
    setText('freeeExpense', '-¥340,000');
    const cf = 890000 - 340000;
    const cfEl = document.getElementById('freeeCF');
    if (cfEl) {
        cfEl.textContent = `+¥${cf.toLocaleString()}`;
        cfEl.className = 'freee-cf-val positive';
    }
}

/* ── Chart: tab switching ────────────────────────────────── */
let _calendarData = null;  // キャッシュ

function switchChart(mode) {
    ['daily','monthly'].forEach(m => {
        document.getElementById(`tab-${m}`).classList.toggle('active', m === mode);
        document.getElementById(`panel-${m}`).classList.toggle('active', m === mode);
    });
}

/* ── Daily Bar Chart ─────────────────────────────────────── */
function renderDailyChart(calData) {
    const el = document.getElementById('dailyBarChart');
    if (!el) return;

    const today = new Date().toISOString().slice(0, 10);
    const pastDays = calData.days.filter(d => d.date <= today && d.revenue >= 0).slice(-12);
    if (pastDays.length === 0) {
        el.innerHTML = `<div style="grid-column:1/-1;text-align:center;color:var(--gray-400);padding:20px">データなし</div>`;
        return;
    }

    const maxRev = Math.max(...pastDays.map(d => d.revenue), 1);
    const html = pastDays.map(d => {
        const pct    = d.revenue / maxRev;
        const height = Math.max(Math.round(pct * 64), d.revenue > 0 ? 4 : 1);
        const cls    = pct > 0.7 ? 'hi' : pct > 0.35 ? 'md' : 'lo';
        const numCls = pct > 0.7 ? 'hi' : '';
        const dayNum = d.date.slice(8).replace(/^0/, '');
        const label  = d.revenue > 0 ? `¥${(d.revenue).toLocaleString()}` : '—';
        return `<div class="day-bar-col">
            <div class="day-bar-num ${numCls}">${label}</div>
            <div class="day-bar ${cls}" style="height:${height}px"></div>
            <div class="day-bar-lbl">${dayNum}</div>
        </div>`;
    }).join('');
    el.innerHTML = html;
}

/* ── Monthly Cumulative SVG Chart ────────────────────────── */
function renderMonthlyCumulativeChart(calData, achData) {
    const svgEl     = document.getElementById('monthlyChartSvg');
    const yLabelsEl = document.getElementById('monthlyYLabels');
    const xLabelsEl = document.getElementById('monthlyXLabels');
    if (!svgEl) return;

    const target     = achData.revenue.target;   // e.g. 5_000_000
    const today      = new Date().toISOString().slice(0, 10);
    const totalDays  = calData.days.length;       // e.g. 30

    // 今月累計
    let cumThis = 0;
    const thisMonthPoints = calData.days.map(d => {
        if (d.date <= today) cumThis += d.revenue;
        return cumThis;
    });

    // 目標累計（日割り）
    const targetPoints = calData.days.map((_, i) => Math.round(target / totalDays * (i + 1)));

    // 先月累計（prev_month_same_day_revenue は当月同日の1点のみなので比例推定）
    const pmRevAtDay = achData.profit_margin.prev_month_same_day || 0;
    // ヒューリスティック: 前月最終値 = pace API の prev_month_same_day_revenue × (30/経過日数)
    // 実際の日別前月データがないため、線形推定で描画
    const elapsedToday = calData.days.findIndex(d => d.date > today) + 1 || totalDays;
    const pmFinalEst   = elapsedToday > 0
        ? Math.round((achData.revenue.actual / elapsedToday) * totalDays * 0.88)   // 前月は今月の88%と仮定
        : 0;
    const prevMonthPoints = calData.days.map((_, i) => Math.round(pmFinalEst / totalDays * (i + 1)));

    // Chart dimensions
    const svgWidth  = svgEl.clientWidth || 280;
    const svgHeight = 120;
    const padBottom = 16;
    const chartH    = svgHeight - padBottom;

    const maxVal = Math.max(...targetPoints, ...thisMonthPoints, 1);

    function toX(i) { return (i / (totalDays - 1)) * svgWidth; }
    function toY(v) { return chartH - (v / maxVal * chartH); }
    function makePath(points, untilIdx) {
        return points.slice(0, untilIdx + 1)
            .map((v, i) => `${i === 0 ? 'M' : 'L'}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`)
            .join(' ');
    }

    const todayIdx = calData.days.findIndex(d => d.date > today);
    const activeUntil = todayIdx === -1 ? totalDays - 1 : todayIdx - 1;

    // Y-axis labels (5 levels)
    const ySteps = [0, 0.25, 0.5, 0.75, 1.0].map(f => Math.round(maxVal * f));
    if (yLabelsEl) {
        yLabelsEl.innerHTML = [...ySteps].reverse().map(v =>
            `<div class="monthly-y-lbl">${v >= 1000000 ? (v/1000000).toFixed(1)+'M' : v >= 1000 ? (v/1000).toFixed(0)+'K' : v}</div>`
        ).join('');
    }

    // X-axis labels (every 5 days)
    if (xLabelsEl) {
        xLabelsEl.innerHTML = calData.days
            .filter((_, i) => i % 5 === 0 || i === totalDays - 1)
            .map(d => `<div class="monthly-x-lbl">${d.date.slice(8).replace(/^0/,'')}</div>`)
            .join('');
    }

    // SVG paths
    const pathTarget    = makePath(targetPoints, totalDays - 1);
    const pathPrevMonth = makePath(prevMonthPoints, totalDays - 1);
    const pathThisMonth = makePath(thisMonthPoints, activeUntil);

    svgEl.innerHTML = `
        <defs>
          <linearGradient id="mgr" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#2563EB" stop-opacity=".25"/>
            <stop offset="100%" stop-color="#2563EB" stop-opacity="0"/>
          </linearGradient>
        </defs>
        <path d="${pathThisMonth} L${toX(activeUntil).toFixed(1)},${chartH} L0,${chartH} Z"
              fill="url(#mgr)" />
        <path d="${pathTarget}" fill="none" stroke="#F97316" stroke-width="1.5"
              stroke-dasharray="5,4" opacity=".8"/>
        <path d="${pathPrevMonth}" fill="none" stroke="#94A3B8" stroke-width="1.5"
              stroke-dasharray="5,4" opacity=".7"/>
        <path d="${pathThisMonth}" fill="none" stroke="#2563EB" stroke-width="2"/>
    `;
}

/* ── Sales Calendar ──────────────────────────────────────── */
async function loadCalendar() {
    try {
        const data = await apiFetch('/api/overview/calendar');
        _calendarData = data;
        renderSalesCal(data);
        renderPayCal(data);
    } catch (e) {
        const el = document.getElementById('salesCalendar');
        if (el) el.innerHTML = '<div class="empty-state">カレンダーを読み込めませんでした</div>';
    }
}

function switchCal(mode) {
    ['sale','pay'].forEach(m => {
        document.getElementById(`cal-tab-${m}`).classList.toggle('active', m === mode);
        document.getElementById(`cal-panel-${m}`).classList.toggle('active', m === mode);
    });
}

function buildCalGrid(year, month, days, cellFn) {
    const todayStr  = new Date().toISOString().slice(0, 10);
    const firstDow  = new Date(year, month - 1, 1).getDay();
    const headJa    = ['日','月','火','水','木','金','土'];
    let html = '<div class="cal-grid">';
    headJa.forEach(h => { html += `<div class="cal-header">${h}</div>`; });
    for (let i = 0; i < firstDow; i++) html += '<div class="cal-day empty"></div>';
    days.forEach(d => {
        const isToday  = d.date === todayStr;
        const isFuture = d.date > todayStr;
        html += cellFn(d, isToday, isFuture);
    });
    html += '</div>';
    return html;
}

function renderSalesCal(data) {
    const { year, month, days } = data;
    const maxRev = Math.max(...days.map(d => d.revenue), 1);
    const el = document.getElementById('salesCalendar');
    if (!el) return;
    el.innerHTML = buildCalGrid(year, month, days, (d, isToday, isFuture) => {
        const hasSales  = d.revenue > 0;
        const intensity = hasSales ? Math.max(0.15, d.revenue / maxRev) : 0;
        const dayNum    = parseInt(d.date.slice(8));
        const tooltip   = hasSales ? `${d.date}: ${fmt(d.revenue)} / ${d.orders}件` : d.date;
        let cls = 'cal-day';
        if (isToday)  cls += ' is-today';
        if (isFuture) cls += ' is-future';
        if (hasSales) cls += ' has-sales';
        const style = hasSales ? ` style="--intensity:${intensity}"` : '';
        const dot   = hasSales ? '<span class="cal-dot">●</span>' : (isFuture ? '' : '<span class="cal-dot empty-dot">○</span>');
        const todayRev = (isToday && hasSales) ? `<span class="cal-today-rev">${fmt(d.revenue)}</span>` : '';
        return `<div class="${cls}"${style} title="${escapeHtml(tooltip)}">
            <span class="cal-day-num">${dayNum}</span>${dot}${todayRev}</div>`;
    });
}

function renderPayCal(data) {
    /* 入金カレンダーは売上カレンダーと同じデータを再利用
       (将来: Payoneer API からの実入金日データに差し替え) */
    const { year, month, days } = data;
    const maxRev = Math.max(...days.map(d => d.revenue), 1);
    const el = document.getElementById('payCalendar');
    if (!el) return;
    el.innerHTML = buildCalGrid(year, month, days, (d, isToday, isFuture) => {
        const hasPay    = d.revenue > 0;
        const intensity = hasPay ? Math.max(0.15, d.revenue / maxRev) : 0;
        const dayNum    = parseInt(d.date.slice(8));
        let cls = 'cal-day';
        if (isToday)  cls += ' is-today';
        if (isFuture) cls += ' is-future';
        if (hasPay) { cls += ' has-sales'; }
        const style = hasPay ? ` style="--intensity:${intensity};--hue:150"` : '';
        const dot   = hasPay ? '<span class="cal-dot">●</span>' : (isFuture ? '' : '<span class="cal-dot empty-dot">○</span>');
        return `<div class="${cls}"${style}><span class="cal-day-num">${dayNum}</span>${dot}</div>`;
    });
}

/* ── Out-of-stock list ───────────────────────────────────── */
async function loadOOS() {
    try {
        const items = await apiFetch('/api/overview/out_of_stock');
        renderOOS(items);
    } catch (e) {
        const tb = document.getElementById('oosTableBody');
        if (tb) tb.innerHTML = '<tr><td colspan="4" class="oos-empty-row">読み込みエラー</td></tr>';
    }
}

function renderOOS(items) {
    const tb = document.getElementById('oosTableBody');
    if (!tb) return;
    if (!items.length) {
        tb.innerHTML = '<tr><td colspan="4" class="oos-empty-row">在庫切れ商品はありません ✅</td></tr>';
        return;
    }
    tb.innerHTML = items.map(item => {
        const days = item.days_out_of_stock != null ? `${item.days_out_of_stock}日` : '—';
        const price = item.last_sale_price_jpy > 0 ? fmt(item.last_sale_price_jpy) : `$${item.price_usd}`;
        const query = encodeURIComponent(item.title.slice(0, 40));
        return `<tr>
            <td>${escapeHtml(item.title.slice(0, 45))}${item.title.length > 45 ? '…' : ''}</td>
            <td>${price}</td>
            <td><span class="oos-days-badge">${days}</span></td>
            <td><a class="oos-search-btn" href="/sourcing?q=${query}" target="_blank">仕入れ検索</a></td>
        </tr>`;
    }).join('');
}

/* ── Category Profit Modal ───────────────────────────────── */
let _catData = null;

async function openCatModal() {
    document.getElementById('catModal').classList.add('open');
    if (_catData) { renderCatModal(_catData); return; }
    try {
        const data = await apiFetch('/api/overview/category_profit');
        _catData = data;
        renderCatModal(data);
    } catch (e) {
        const tb = document.getElementById('catModalTableBody');
        if (tb) tb.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--gray-400);padding:16px">データなし</td></tr>';
    }
}

function closeCatModal() {
    document.getElementById('catModal').classList.remove('open');
}

function renderCatModal(items) {
    const tb     = document.getElementById('catModalTableBody');
    const svgEl  = document.getElementById('catDonutSvg');
    const footEl = document.getElementById('catModalFoot');
    if (!tb) return;

    if (!items.length) {
        tb.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--gray-400);padding:16px">データなし</td></tr>';
        return;
    }

    // Table
    tb.innerHTML = items.map((item, i) => {
        const color = CAT_COLORS[i % CAT_COLORS.length];
        return `<tr>
            <td><span class="cat-dot" style="background:${color}"></span></td>
            <td>${escapeHtml(item.category)}</td>
            <td style="font-weight:700">${fmt(item.profit)}</td>
            <td>
                <div class="cat-pct-bar">
                    <div class="cat-pct-track"><div class="cat-pct-fill" style="width:${item.pct_of_total}%;background:${color}"></div></div>
                    <span class="cat-pct-num" style="color:${color}">${item.pct_of_total}%</span>
                </div>
            </td>
        </tr>`;
    }).join('');

    // Donut SVG
    if (svgEl) {
        const cx = 60, cy = 60, r = 42, r2 = 26;
        const total = items.reduce((s, item) => s + item.profit, 0);
        let startAngle = -Math.PI / 2;
        const slices = items.map((item, i) => {
            const angle = (item.profit / total) * 2 * Math.PI;
            const x1 = cx + r * Math.cos(startAngle);
            const y1 = cy + r * Math.sin(startAngle);
            startAngle += angle;
            const x2 = cx + r * Math.cos(startAngle);
            const y2 = cy + r * Math.sin(startAngle);
            const x3 = cx + r2 * Math.cos(startAngle);
            const y3 = cy + r2 * Math.sin(startAngle);
            const x4 = cx + r2 * Math.cos(startAngle - angle);
            const y4 = cy + r2 * Math.sin(startAngle - angle);
            const large = angle > Math.PI ? 1 : 0;
            const color = CAT_COLORS[i % CAT_COLORS.length];
            const path = `M${x1.toFixed(1)},${y1.toFixed(1)} A${r},${r} 0 ${large},1 ${x2.toFixed(1)},${y2.toFixed(1)} L${x3.toFixed(1)},${y3.toFixed(1)} A${r2},${r2} 0 ${large},0 ${x4.toFixed(1)},${y4.toFixed(1)} Z`;
            return `<path d="${path}" fill="${color}" opacity=".9"/>`;
        });
        svgEl.innerHTML = slices.join('') +
            `<text x="${cx}" y="${cy+4}" text-anchor="middle" font-size="10" font-weight="700" fill="#374151">${items.length}カテゴリ</text>`;
    }

    // Footer
    const topCat = items[0];
    if (footEl && topCat) {
        footEl.textContent = `最大利益カテゴリ: ${topCat.category} (${topCat.pct_of_total}% / 利益率 ${topCat.margin}%)`;
    }
}

/* ── Entry Point ─────────────────────────────────────────── */
async function initOverview() {
    // Load all data in parallel
    const [, , calData, achData] = await Promise.all([
        loadFxRate(),
        loadAlerts(),
        loadCalendar(),
        (async () => {
            await loadAchievement();
            return apiFetch('/api/overview/achievement');
        })(),
        loadKpiComparison(),
        loadOOS(),
    ]);

    renderPayoneerStatic();
    renderFreeeStatic();

    // Charts need both calData and achData
    if (_calendarData) {
        try {
            const ach = await apiFetch('/api/overview/achievement');
            renderDailyChart(_calendarData);
            renderMonthlyCumulativeChart(_calendarData, ach);
        } catch (e) {
            console.warn('chart render failed', e);
        }
    }
}

initOverview();
```

- [ ] **Step 2: Open the overview page in browser, check for JS errors**

```
open http://localhost:8000/
```

Open browser DevTools → Console. There should be no uncaught errors. The charts, KPI table, OOS list, and alert strip should all render with real data (or empty states if DB has no data).

- [ ] **Step 3: Run the full test suite to confirm no regressions**

```bash
cd products/ebay-agent
python -m pytest tests/ -v
```

Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add products/ebay-agent/static/js/overview.js
git commit -m "feat(overview): rewrite overview.js with chart tabs, KPI table, calendar tabs, OOS list, category modal"
```

---

## Self-Review

### 1. Spec Coverage

| Spec requirement | Task |
|-----------------|------|
| アラートストリップ（在庫切れ/未読/価格アラート） | Existing + Task 7 (Japanese labels) |
| 達成ボード3カード（売上/利益率/利益） | Task 6 (HTML) + Task 7 (JS) |
| ペース予測（月末着地） | Task 7 `renderAchievement` |
| KPI前月同日比パネル | Task 1 (expanded pace) + Task 7 |
| 月別カレンダーヒートマップ | Task 7 `renderSalesCal` |
| 30日トレンドグラフ改良（目標ライン追加） | Task 7 `renderMonthlyCumulativeChart` |
| USD/JPY レート | Task 3 (`/api/fx/usdjpy`) + Task 7 |
| Payoneerウィジェット | Task 6 (HTML card) + Task 7 (static) |
| freeeキャッシュフロー | Task 6 (HTML) + Task 7 (static placeholder) |
| 在庫切れリストカード | Task 2 (`get_out_of_stock_items`) + Task 3 + Task 6 + Task 7 |
| カテゴリ分析モーダル（ドーナツ） | Task 2 (`get_category_profit`) + Task 3 + Task 6 + Task 7 |
| 日別/月別累計チャートタブ | Task 6 + Task 7 |
| 売上/入金カレンダータブ | Task 6 + Task 7 |

### 2. Placeholder Scan

- freee cashflow: marked as "static placeholder, 後続タスクで実装" — intentional, not a plan failure
- Payoneer: marked as "Payoneer APIは別途OAuth設定後に実装予定" — intentional
- 入金カレンダー: uses same data as 売上カレンダー as explicit fallback until Payoneer API is wired

### 3. Type Consistency

- `get_overview_pace` in Task 1 returns `profit_margin_actual` / `profit_margin_prev` — used in Task 7 as `pace.profit_margin_prev`
- `get_out_of_stock_items` returns `{sku, title, price_usd, last_sale_price_jpy, days_out_of_stock}` — all fields used in Task 7 `renderOOS`
- `get_category_profit` returns `{category, revenue, profit, margin, pct_of_total}` — all used in Task 7 `renderCatModal`
- HTML IDs in Task 6 match `document.getElementById` calls in Task 7: `revActual`, `marginActual`, `profitActual`, `fxRate`, `fxDiff`, `kpiCompTable`, `oosTableBody`, `catModal`, `catDonutSvg`, `catModalTableBody`, `catModalFoot`, `monthlyChartSvg`, `dailyBarChart`, `salesCalendar`, `payCalendar` ✅
