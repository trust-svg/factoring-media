# eBay Agent Hub Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Overview ページを「入金達成ボード＋カレンダーヒートマップ＋アラートストリップ＋ペース予測」付きのダッシュボードに刷新し、3秒で今月の状態が把握できるUIにする。

**Architecture:** 4本の新規 GET API（/api/overview/\*）を `main.py` に追加し、CRUD クエリを `database/crud.py` に実装。フロントは `overview.js`（新規）に移し、`overview.html` を全面刷新。`config.py` に月間目標値定数を追加。DB スキーマ変更なし。

**Tech Stack:** FastAPI, SQLAlchemy（SQLite）, Vanilla JS, ApexCharts, CSS Variables

---

## File Map

| ファイル | 種別 | 役割 |
|---------|------|------|
| `products/ebay-agent/config.py` | Modify | 月間目標値定数3つ追加 |
| `products/ebay-agent/database/crud.py` | Modify | 新規クエリ4関数追加 |
| `products/ebay-agent/tests/test_overview_crud.py` | Create | CRUDユニットテスト |
| `products/ebay-agent/main.py` | Modify | 新規APIエンドポイント4本追加 |
| `products/ebay-agent/static/css/style.css` | Modify | アラートストリップ・達成ボード・カレンダーCSS追加 |
| `products/ebay-agent/static/js/overview.js` | Create | Overview専用JS（既存インラインを移植＋新機能） |
| `products/ebay-agent/templates/pages/overview.html` | Modify | 全面レイアウト刷新 |

---

## Task 1: config.py — 月間目標定数

**Files:**
- Modify: `products/ebay-agent/config.py`

- [ ] **Step 1: 定数を追加する**

`config.py` の末尾（`SHOPIFY_DISCOUNT_RATE` の行の後）に追加：

```python
# ── Monthly Targets ───────────────────────────────────────
MONTHLY_REVENUE_TARGET_JPY = 5_000_000   # ¥5,000,000
MONTHLY_MARGIN_TARGET_PCT  = 20.0        # 20%
MONTHLY_PROFIT_TARGET_JPY  = 1_000_000   # ¥1,000,000
```

- [ ] **Step 2: インポート確認**

```bash
cd products/ebay-agent
python -c "from config import MONTHLY_REVENUE_TARGET_JPY, MONTHLY_MARGIN_TARGET_PCT, MONTHLY_PROFIT_TARGET_JPY; print(MONTHLY_REVENUE_TARGET_JPY, MONTHLY_MARGIN_TARGET_PCT, MONTHLY_PROFIT_TARGET_JPY)"
```

期待出力: `5000000 20.0 1000000`

- [ ] **Step 3: Commit**

```bash
git add products/ebay-agent/config.py
git commit -m "feat: add monthly target constants to config"
```

---

## Task 2: database/crud.py — 新規クエリ関数4つ

**Files:**
- Modify: `products/ebay-agent/database/crud.py`

- [ ] **Step 1: ファイル末尾にインポートと4関数を追加する**

`crud.py` の末尾に追加（既存の `get_dashboard_stats` 関数の後）：

```python
# ── Overview ダッシュボード用クエリ ───────────────────────

def get_monthly_achievement(db: Session, year: int, month: int) -> dict:
    """当月の売上・利益・利益率を集計し、目標との比較を返す"""
    from calendar import monthrange
    from datetime import datetime, date
    from config import MONTHLY_REVENUE_TARGET_JPY, MONTHLY_MARGIN_TARGET_PCT, MONTHLY_PROFIT_TARGET_JPY

    _, last_day = monthrange(year, month)
    start = datetime(year, month, 1)
    end = datetime(year, month, last_day, 23, 59, 59)

    records = db.query(SalesRecord).filter(
        SalesRecord.sold_at >= start,
        SalesRecord.sold_at <= end,
    ).all()

    today = date.today()
    # elapsed_days: 当月1日 = 1, 2日 = 2...（当月内の場合）
    elapsed_days = today.day if (today.year == year and today.month == month) else last_day

    # 売上JPY: received_jpy > 0 ならそれ、なければ sale_price_usd * exchange_rate
    def _rev(r: SalesRecord) -> int:
        if r.received_jpy > 0:
            return r.received_jpy
        if r.exchange_rate > 0:
            return int(r.sale_price_usd * r.exchange_rate)
        return 0

    revenue_jpy = sum(_rev(r) for r in records)
    profit_jpy  = sum(r.net_profit_jpy for r in records)
    margin_pct  = round(profit_jpy / revenue_jpy * 100, 1) if revenue_jpy > 0 else 0.0

    projected_revenue = int(revenue_jpy / elapsed_days * last_day) if elapsed_days > 0 else 0
    projected_profit  = int(profit_jpy  / elapsed_days * last_day) if elapsed_days > 0 else 0

    # 利益率の前月同日比
    if month == 1:
        pm_year, pm_month = year - 1, 12
    else:
        pm_year, pm_month = year, month - 1

    _, pm_last = monthrange(pm_year, pm_month)
    pm_day = min(elapsed_days, pm_last)
    pm_records = db.query(SalesRecord).filter(
        SalesRecord.sold_at >= datetime(pm_year, pm_month, 1),
        SalesRecord.sold_at <= datetime(pm_year, pm_month, pm_day, 23, 59, 59),
    ).all()
    pm_rev = sum(_rev(r) for r in pm_records)
    pm_profit = sum(r.net_profit_jpy for r in pm_records)
    pm_margin = round(pm_profit / pm_rev * 100, 1) if pm_rev > 0 else 0.0

    return {
        "period": f"{year}-{month:02d}",
        "elapsed_days": elapsed_days,
        "total_days": last_day,
        "revenue": {
            "actual": revenue_jpy,
            "target": MONTHLY_REVENUE_TARGET_JPY,
            "rate": round(revenue_jpy / MONTHLY_REVENUE_TARGET_JPY * 100, 1),
            "projected_eom": projected_revenue,
        },
        "profit_margin": {
            "actual": margin_pct,
            "target": MONTHLY_MARGIN_TARGET_PCT,
            "prev_month_same_day": pm_margin,
        },
        "profit": {
            "actual": profit_jpy,
            "target": MONTHLY_PROFIT_TARGET_JPY,
            "rate": round(profit_jpy / MONTHLY_PROFIT_TARGET_JPY * 100, 1),
            "projected_eom": projected_profit,
        },
    }


def get_monthly_calendar(db: Session, year: int, month: int) -> dict:
    """月間の日別売上データ（カレンダー表示用）"""
    from calendar import monthrange
    from datetime import datetime

    _, last_day = monthrange(year, month)
    start = datetime(year, month, 1)
    end = datetime(year, month, last_day, 23, 59, 59)

    records = db.query(SalesRecord).filter(
        SalesRecord.sold_at >= start,
        SalesRecord.sold_at <= end,
    ).all()

    def _rev(r: SalesRecord) -> int:
        if r.received_jpy > 0:
            return r.received_jpy
        if r.exchange_rate > 0:
            return int(r.sale_price_usd * r.exchange_rate)
        return 0

    # 日付ごとに集計
    daily: dict[str, dict] = {}
    for r in records:
        d = r.sold_at.strftime("%Y-%m-%d")
        if d not in daily:
            daily[d] = {"revenue": 0, "orders": 0, "profit": 0}
        daily[d]["revenue"] += _rev(r)
        daily[d]["orders"]  += 1
        daily[d]["profit"]  += r.net_profit_jpy

    days = []
    for day in range(1, last_day + 1):
        d = f"{year}-{month:02d}-{day:02d}"
        entry = daily.get(d, {"revenue": 0, "orders": 0, "profit": 0})
        days.append({"date": d, **entry})

    return {"year": year, "month": month, "days": days}


def get_overview_alerts(db: Session) -> dict:
    """要対応件数（在庫切れ・未読メッセージ・価格アラート）"""
    out_of_stock = db.query(Listing).filter(Listing.quantity == 0).count()
    unread_messages = db.query(BuyerMessage).filter(
        BuyerMessage.is_read == 0,
        BuyerMessage.direction == "inbound",
    ).count()

    # 価格アラート: 最新の価格履歴で競合最安値が自社より10%以上安い出品
    from sqlalchemy import text as sa_text
    price_alerts = db.execute(sa_text("""
        SELECT COUNT(*) FROM price_history ph
        INNER JOIN (
            SELECT sku, MAX(recorded_at) AS max_at FROM price_history GROUP BY sku
        ) latest ON ph.sku = latest.sku AND ph.recorded_at = latest.max_at
        INNER JOIN listings l ON ph.sku = l.sku
        WHERE ph.lowest_competitor_price_usd > 0
          AND ph.lowest_competitor_price_usd < l.price_usd * 0.9
    """)).scalar() or 0

    severity = "ok"
    if out_of_stock >= 10 or unread_messages >= 5:
        severity = "critical"
    elif out_of_stock > 0 or unread_messages > 0 or price_alerts > 0:
        severity = "warning"

    return {
        "out_of_stock": out_of_stock,
        "unread_messages": unread_messages,
        "price_alerts": int(price_alerts),
        "severity": severity,
    }


def get_overview_pace(db: Session) -> dict:
    """今日の売上・前月同日比"""
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

    today_records = db.query(SalesRecord).filter(
        SalesRecord.sold_at >= today_start,
        SalesRecord.sold_at <= today_end,
    ).all()
    today_revenue = sum(_rev(r) for r in today_records)
    today_orders  = len(today_records)

    # 当月累計（今日を除く）
    month_start = datetime(today.year, today.month, 1)
    yesterday_end = today_start - timedelta(seconds=1)
    prior_records = db.query(SalesRecord).filter(
        SalesRecord.sold_at >= month_start,
        SalesRecord.sold_at <= yesterday_end,
    ).all()
    prior_revenue  = sum(_rev(r) for r in prior_records)
    elapsed_before = today.day - 1  # 今日より前の日数
    daily_avg = int(prior_revenue / elapsed_before) if elapsed_before > 0 else 0

    # 前月同日時点の累計
    if today.month == 1:
        pm_year, pm_month = today.year - 1, 12
    else:
        pm_year, pm_month = today.year, today.month - 1

    _, pm_last = monthrange(pm_year, pm_month)
    pm_day = min(today.day, pm_last)
    pm_records = db.query(SalesRecord).filter(
        SalesRecord.sold_at >= datetime(pm_year, pm_month, 1),
        SalesRecord.sold_at <= datetime(pm_year, pm_month, pm_day, 23, 59, 59),
    ).all()
    pm_revenue = sum(_rev(r) for r in pm_records)

    current_total = prior_revenue + today_revenue
    rev_diff     = current_total - pm_revenue
    rev_diff_pct = round(rev_diff / pm_revenue * 100, 1) if pm_revenue > 0 else 0.0

    return {
        "today_revenue": today_revenue,
        "today_orders":  today_orders,
        "daily_avg":     daily_avg,
        "prev_month_same_day_revenue": pm_revenue,
        "prev_month_comparison": {
            "revenue_diff":     rev_diff,
            "revenue_diff_pct": rev_diff_pct,
        },
    }
```

- [ ] **Step 2: Commit**

```bash
git add products/ebay-agent/database/crud.py
git commit -m "feat: add overview CRUD queries (achievement, calendar, alerts, pace)"
```

---

## Task 3: tests/test_overview_crud.py — ユニットテスト

**Files:**
- Create: `products/ebay-agent/tests/__init__.py`
- Create: `products/ebay-agent/tests/test_overview_crud.py`

- [ ] **Step 1: tests ディレクトリと __init__.py を作成**

```bash
mkdir -p products/ebay-agent/tests
touch products/ebay-agent/tests/__init__.py
```

- [ ] **Step 2: テストを書く**

`products/ebay-agent/tests/test_overview_crud.py`：

```python
"""Overview CRUD クエリのユニットテスト（インメモリ SQLite）"""
import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# プロジェクトルートを sys.path に追加
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.models import Base, SalesRecord, Listing, BuyerMessage
from database.crud import (
    get_monthly_achievement,
    get_monthly_calendar,
    get_overview_alerts,
    get_overview_pace,
)


@pytest.fixture
def db():
    """インメモリ DB セッション"""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _sale(sold_at, received_jpy=10000, net_profit_jpy=2000, margin=20.0, exchange_rate=150.0, sale_price_usd=66.67):
    return SalesRecord(
        order_id=f"order-{sold_at}",
        sku="TEST-SKU",
        title="Test Item",
        sold_at=sold_at,
        received_jpy=received_jpy,
        net_profit_jpy=net_profit_jpy,
        profit_margin_pct=margin,
        exchange_rate=exchange_rate,
        sale_price_usd=sale_price_usd,
        net_profit_usd=net_profit_jpy / exchange_rate,
    )


def test_get_monthly_achievement_empty(db):
    result = get_monthly_achievement(db, 2026, 4)
    assert result["revenue"]["actual"] == 0
    assert result["profit"]["actual"] == 0
    assert result["revenue"]["target"] == 5_000_000
    assert result["profit"]["target"] == 1_000_000


def test_get_monthly_achievement_with_data(db):
    db.add(_sale(datetime(2026, 4, 1), received_jpy=100_000, net_profit_jpy=20_000))
    db.add(_sale(datetime(2026, 4, 5), received_jpy=200_000, net_profit_jpy=40_000))
    db.commit()

    result = get_monthly_achievement(db, 2026, 4)
    assert result["revenue"]["actual"] == 300_000
    assert result["profit"]["actual"] == 60_000
    assert result["profit_margin"]["actual"] == 20.0


def test_get_monthly_calendar_groups_by_day(db):
    db.add(_sale(datetime(2026, 4, 1, 10, 0), received_jpy=50_000, net_profit_jpy=10_000))
    db.add(_sale(datetime(2026, 4, 1, 15, 0), received_jpy=30_000, net_profit_jpy=6_000))
    db.add(_sale(datetime(2026, 4, 3, 9, 0),  received_jpy=80_000, net_profit_jpy=16_000))
    db.commit()

    result = get_monthly_calendar(db, 2026, 4)
    assert result["year"] == 2026
    assert result["month"] == 4
    assert len(result["days"]) == 30  # April has 30 days

    day1 = next(d for d in result["days"] if d["date"] == "2026-04-01")
    assert day1["revenue"] == 80_000
    assert day1["orders"] == 2

    day3 = next(d for d in result["days"] if d["date"] == "2026-04-03")
    assert day3["revenue"] == 80_000
    assert day3["orders"] == 1

    day2 = next(d for d in result["days"] if d["date"] == "2026-04-02")
    assert day2["revenue"] == 0


def test_get_overview_alerts_severity(db):
    # 空データ → ok
    result = get_overview_alerts(db)
    assert result["severity"] == "ok"
    assert result["out_of_stock"] == 0
    assert result["unread_messages"] == 0

    # 在庫切れ追加 → warning
    db.add(Listing(sku="A", quantity=0))
    db.commit()
    result = get_overview_alerts(db)
    assert result["severity"] == "warning"
    assert result["out_of_stock"] == 1

    # 在庫切れ10件以上 → critical
    for i in range(10):
        db.add(Listing(sku=f"OOS-{i}", quantity=0))
    db.commit()
    result = get_overview_alerts(db)
    assert result["severity"] == "critical"


def test_get_overview_pace_no_data(db):
    result = get_overview_pace(db)
    assert result["today_revenue"] == 0
    assert result["today_orders"] == 0
    assert result["prev_month_same_day_revenue"] == 0
```

- [ ] **Step 3: テストを実行してすべてパスすることを確認**

```bash
cd products/ebay-agent
pip install pytest -q
pytest tests/test_overview_crud.py -v
```

期待出力（5テスト全パス）:
```
tests/test_overview_crud.py::test_get_monthly_achievement_empty PASSED
tests/test_overview_crud.py::test_get_monthly_achievement_with_data PASSED
tests/test_overview_crud.py::test_get_monthly_calendar_groups_by_day PASSED
tests/test_overview_crud.py::test_get_overview_alerts_severity PASSED
tests/test_overview_crud.py::test_get_overview_pace_no_data PASSED
```

- [ ] **Step 4: Commit**

```bash
git add products/ebay-agent/tests/
git commit -m "test: add overview CRUD unit tests"
```

---

## Task 4: main.py — 新規APIエンドポイント4本

**Files:**
- Modify: `products/ebay-agent/main.py`

- [ ] **Step 1: config インポートに新定数を追加**

`main.py` の既存インポート行（6行目あたり）を更新：

```python
from config import (
    APP_HOST, APP_PORT, DEAL_WATCHER_DB, EBAY_FEE_RATE, PAYONEER_FEE_RATE,
    PRICE_CHECK_INTERVAL_HOURS, SHOPIFY_WEBHOOK_SECRET, STATIC_DIR, TEMPLATES_DIR,
    MONTHLY_REVENUE_TARGET_JPY, MONTHLY_MARGIN_TARGET_PCT, MONTHLY_PROFIT_TARGET_JPY,
)
```

- [ ] **Step 2: 4本のエンドポイントを main.py の末尾（`if __name__ == "__main__":` の手前）に追加**

```python
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
```

- [ ] **Step 3: サーバーを起動してエンドポイントを手動確認**

```bash
cd products/ebay-agent
uvicorn main:app --reload --port 8000 &
sleep 3
curl -s http://localhost:8000/api/overview/achievement | python -m json.tool
curl -s http://localhost:8000/api/overview/calendar | python -m json.tool | head -30
curl -s http://localhost:8000/api/overview/alerts | python -m json.tool
curl -s http://localhost:8000/api/overview/pace | python -m json.tool
```

各エンドポイントが 200 OK で JSON を返すことを確認。エラーがあれば修正。

- [ ] **Step 4: Commit**

```bash
git add products/ebay-agent/main.py
git commit -m "feat: add /api/overview/* endpoints (achievement, calendar, alerts, pace)"
```

---

## Task 5: static/css/style.css — 新コンポーネントCSS

**Files:**
- Modify: `products/ebay-agent/static/css/style.css`

- [ ] **Step 1: ファイル末尾に以下を追加**

```css
/* ════════════════════════════════════════════════════════
   Overview Dashboard — Redesign Components
   ════════════════════════════════════════════════════════ */

/* ── Alert Strip ─────────────────────────────────────── */
.alert-strip {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    padding: 10px 16px;
    border-radius: 12px;
    margin-bottom: 20px;
    background: var(--warning-50);
    border: 1px solid var(--warning-100);
}
.alert-strip.critical {
    background: var(--error-50);
    border-color: var(--error-100);
}
.alert-strip .alert-item {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: 500;
    background: white;
    color: var(--warning-700);
    border: 1px solid var(--warning-100);
    text-decoration: none;
    transition: var(--transition-fast);
}
.alert-strip .alert-item:hover { opacity: 0.8; }
.alert-strip .alert-item.critical {
    color: var(--error-600);
    border-color: var(--error-100);
}

/* ── Achievement Board ───────────────────────────────── */
.achievement-board {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
    margin-bottom: 20px;
}
@media (max-width: 900px) {
    .achievement-board { grid-template-columns: 1fr; }
}
.achievement-card {
    background: var(--bg-secondary);
    border-radius: 16px;
    padding: 24px;
    border: 1px solid var(--border);
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}
.achievement-card .ach-label {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-muted);
    margin-bottom: 8px;
}
.achievement-card .ach-values {
    display: flex;
    align-items: baseline;
    gap: 6px;
    margin-bottom: 12px;
}
.achievement-card .ach-actual {
    font-size: 28px;
    font-weight: 800;
    color: var(--text-primary);
    letter-spacing: -1px;
}
.achievement-card .ach-target {
    font-size: 14px;
    color: var(--text-muted);
}
.progress-wrap {
    height: 8px;
    background: var(--gray-100);
    border-radius: 99px;
    overflow: hidden;
    margin-bottom: 10px;
}
.progress-bar {
    height: 100%;
    border-radius: 99px;
    background: var(--blue);
    transition: width 0.6s cubic-bezier(0.4,0,0.2,1);
    min-width: 4px;
}
.achievement-card .ach-meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12px;
}
.achievement-card .ach-rate {
    font-weight: 700;
    color: var(--text-primary);
}
.achievement-card .ach-pace {
    color: var(--text-muted);
    font-size: 11px;
}
.achievement-card .ach-pace.on-track { color: var(--green); }
.achievement-card .ach-pace.off-track { color: var(--red); }

/* ── Overview Main Grid ──────────────────────────────── */
.overview-main-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-bottom: 20px;
}
@media (max-width: 900px) {
    .overview-main-grid { grid-template-columns: 1fr; }
}

/* ── KPI Comparison Panel ────────────────────────────── */
.kpi-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 0;
    border-bottom: 1px solid var(--gray-100);
}
.kpi-row:last-child { border-bottom: none; }
.kpi-row .kpi-label { font-size: 13px; color: var(--text-secondary); }
.kpi-row .kpi-value { font-size: 15px; font-weight: 600; color: var(--text-primary); }
.kpi-row .kpi-diff {
    font-size: 12px;
    font-weight: 500;
    padding: 2px 8px;
    border-radius: 12px;
    min-width: 60px;
    text-align: center;
}
.kpi-row .kpi-diff.up { background: var(--success-50); color: var(--success-700); }
.kpi-row .kpi-diff.down { background: var(--error-50); color: var(--error-600); }
.kpi-row .kpi-diff.neutral { background: var(--gray-100); color: var(--gray-500); }

/* ── Sales Calendar ──────────────────────────────────── */
.cal-grid {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 3px;
}
.cal-header {
    text-align: center;
    font-size: 10px;
    font-weight: 700;
    color: var(--text-muted);
    padding: 4px 0;
    text-transform: uppercase;
}
.cal-day {
    aspect-ratio: 1;
    border-radius: 8px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    color: var(--text-secondary);
    background: var(--gray-50);
    cursor: default;
    position: relative;
    transition: var(--transition-fast);
}
.cal-day.empty { background: transparent; }
.cal-day.is-future { opacity: 0.3; }
.cal-day.has-sales {
    background: rgba(0, 122, 255, calc(var(--intensity, 0.2)));
    color: var(--text-primary);
    font-weight: 600;
}
.cal-day.is-today {
    border: 2px solid var(--blue);
    background: var(--blue-light);
    color: var(--blue);
    font-weight: 700;
}
.cal-day-num { line-height: 1; }
.cal-dot { font-size: 8px; margin-top: 2px; color: var(--blue); }
.cal-dot.empty-dot { color: var(--gray-300); }
.cal-today-rev {
    position: absolute;
    bottom: 2px;
    font-size: 8px;
    color: var(--blue-dark);
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    max-width: 90%;
    text-overflow: ellipsis;
}
```

- [ ] **Step 2: ブラウザで CSS が壊れていないことを確認（既存ページの表示確認）**

```bash
# サーバーが起動中の状態で
open http://localhost:8000/
```

既存のデザインが崩れていないこと（サイドバー・ヘッダー・stat-card が正常表示）を確認。

- [ ] **Step 3: Commit**

```bash
git add products/ebay-agent/static/css/style.css
git commit -m "feat: add achievement board, calendar, alert strip CSS"
```

---

## Task 6: static/js/overview.js — 新規JSファイル

**Files:**
- Create: `products/ebay-agent/static/js/overview.js`

- [ ] **Step 1: ファイルを作成**

`products/ebay-agent/static/js/overview.js`：

```javascript
/* eBay Agent Hub — Overview Dashboard JS */

/* ── Helpers ── */
const fmt = (n) => formatJPY(n);   // from app.js
const pct = (n) => formatPct(n);   // from app.js

const MONTH_NAMES    = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const MONTH_NAMES_JA = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'];

/* ── Alert Strip ── */
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
        items.push(`<a href="/listings" class="alert-item ${cls}">⚠️ Out of Stock: ${data.out_of_stock}</a>`);
    }
    if (data.unread_messages > 0) {
        const cls = data.unread_messages >= 5 ? 'critical' : '';
        items.push(`<a href="/chat" class="alert-item ${cls}">💬 Unread Messages: ${data.unread_messages}</a>`);
    }
    if (data.price_alerts > 0) {
        items.push(`<a href="/listings?tab=pricing" class="alert-item">📉 Price Alerts: ${data.price_alerts}</a>`);
    }
    if (items.length === 0) {
        strip.style.display = 'none';
        return;
    }
    strip.innerHTML = items.join('');
    strip.style.display = 'flex';
    strip.className = `alert-strip ${data.severity}`;
}

/* ── Achievement Board ── */
async function loadAchievement() {
    try {
        const data = await apiFetch('/api/overview/achievement');
        renderAchievement(data);
    } catch (e) {
        console.warn('achievement load failed', e);
    }
}

function setProgressBar(barId, ratePct, color) {
    const bar = document.getElementById(barId);
    if (!bar) return;
    const capped = Math.min(ratePct, 100);
    bar.style.width = capped + '%';
    bar.style.background = color;
}

function renderAchievement(data) {
    const rev    = data.revenue;
    const margin = data.profit_margin;
    const profit = data.profit;

    /* Revenue card */
    const revColor = rev.rate >= 100 ? 'var(--green)' : 'var(--blue)';
    if (document.getElementById('revActual'))
        document.getElementById('revActual').textContent = fmt(rev.actual);
    setProgressBar('revBar', rev.rate, revColor);
    if (document.getElementById('revRate'))
        document.getElementById('revRate').textContent = pct(rev.rate);
    const revPaceEl = document.getElementById('revPace');
    if (revPaceEl) {
        const icon = rev.projected_eom >= rev.target ? '✅' : '📉';
        const cls  = rev.projected_eom >= rev.target ? 'on-track' : 'off-track';
        revPaceEl.textContent = `Projected: ${fmt(rev.projected_eom)} ${icon}`;
        revPaceEl.className = `ach-pace ${cls}`;
    }

    /* Margin card */
    const marginRatePct = margin.target > 0 ? margin.actual / margin.target * 100 : 0;
    const marginColor   = marginRatePct >= 100 ? 'var(--green)' : marginRatePct >= 80 ? 'var(--orange)' : 'var(--red)';
    if (document.getElementById('marginActual'))
        document.getElementById('marginActual').textContent = pct(margin.actual);
    setProgressBar('marginBar', marginRatePct, marginColor);
    if (document.getElementById('marginRate'))
        document.getElementById('marginRate').textContent = `${pct(margin.actual)} / ${pct(margin.target)}`;
    const marginPaceEl = document.getElementById('marginPace');
    if (marginPaceEl) {
        const diff = margin.actual - (margin.prev_month_same_day || 0);
        const sign = diff >= 0 ? '+' : '';
        const cls  = diff >= 0 ? 'on-track' : 'off-track';
        marginPaceEl.textContent = `vs last month: ${sign}${diff.toFixed(1)}pp`;
        marginPaceEl.className = `ach-pace ${cls}`;
    }

    /* Profit card */
    const profitColor = profit.rate >= 100 ? 'var(--green)' : 'var(--indigo)';
    if (document.getElementById('profitActual'))
        document.getElementById('profitActual').textContent = fmt(profit.actual);
    setProgressBar('profitBar', profit.rate, profitColor);
    if (document.getElementById('profitRate'))
        document.getElementById('profitRate').textContent = pct(profit.rate);
    const profitPaceEl = document.getElementById('profitPace');
    if (profitPaceEl) {
        const icon = profit.projected_eom >= profit.target ? '✅' : '📉';
        const cls  = profit.projected_eom >= profit.target ? 'on-track' : 'off-track';
        profitPaceEl.textContent = `Projected: ${fmt(profit.projected_eom)} ${icon}`;
        profitPaceEl.className = `ach-pace ${cls}`;
    }
}

/* ── Sales Calendar ── */
async function loadCalendar() {
    try {
        const data = await apiFetch('/api/overview/calendar');
        renderCalendar(data);
    } catch (e) {
        const el = document.getElementById('salesCalendar');
        if (el) el.innerHTML = '<div class="empty-state">Could not load calendar</div>';
    }
}

function renderCalendar(data) {
    const { year, month, days } = data;
    const todayStr = new Date().toISOString().slice(0, 10);
    const maxRev   = Math.max(...days.map(d => d.revenue), 1);
    const firstDow = new Date(year, month - 1, 1).getDay(); // 0=Sun

    const cal     = document.getElementById('salesCalendar');
    const titleEl = document.getElementById('calendarTitle');
    if (!cal) return;

    if (titleEl) {
        const mName = t(MONTH_NAMES[month - 1], MONTH_NAMES_JA[month - 1]);
        titleEl.textContent = `${mName} ${year} Sales Calendar`;
    }

    const headers = ['Su','Mo','Tu','We','Th','Fr','Sa'];
    const headJa  = ['日','月','火','水','木','金','土'];
    let html = '<div class="cal-grid">';
    headers.forEach((h, i) => {
        html += `<div class="cal-header">${t(h, headJa[i])}</div>`;
    });

    // 先頭の空マス
    for (let i = 0; i < firstDow; i++) {
        html += '<div class="cal-day empty"></div>';
    }

    days.forEach(d => {
        const isToday  = d.date === todayStr;
        const isFuture = d.date > todayStr;
        const hasSales = d.revenue > 0;
        const intensity = hasSales ? Math.max(0.15, d.revenue / maxRev * 0.85) : 0;
        const dayNum    = parseInt(d.date.slice(8));
        const tooltip   = hasSales
            ? `${d.date}: ${fmt(d.revenue)} / ${d.orders} orders`
            : d.date;

        let cls = 'cal-day';
        if (isToday)  cls += ' is-today';
        if (isFuture) cls += ' is-future';
        if (hasSales) cls += ' has-sales';

        const style = hasSales ? ` style="--intensity:${intensity}"` : '';
        const dotHtml = hasSales
            ? '<span class="cal-dot">●</span>'
            : (isFuture ? '' : '<span class="cal-dot empty-dot">○</span>');
        const todayRevHtml = (isToday && hasSales)
            ? `<span class="cal-today-rev">${fmt(d.revenue)}</span>`
            : '';

        html += `<div class="${cls}"${style} title="${escapeHtml(tooltip)}">
            <span class="cal-day-num">${dayNum}</span>
            ${dotHtml}
            ${todayRevHtml}
        </div>`;
    });

    html += '</div>';
    cal.innerHTML = html;
}

/* ── KPI Comparison (Pace) ── */
async function loadPace() {
    try {
        const data = await apiFetch('/api/overview/pace');
        renderPace(data);
    } catch (e) {
        const el = document.getElementById('kpiTable');
        if (el) el.innerHTML = '<div class="empty-state">Could not load KPI data</div>';
    }
}

function renderPace(data) {
    const { today_revenue, today_orders, daily_avg, prev_month_comparison } = data;
    const { revenue_diff, revenue_diff_pct } = prev_month_comparison;

    const sign  = revenue_diff >= 0 ? '+' : '';
    const arrow = revenue_diff >= 0 ? '↑' : '↓';
    const diffCls = revenue_diff >= 0 ? 'up' : 'down';

    const kpiTable = document.getElementById('kpiTable');
    if (!kpiTable) return;

    kpiTable.innerHTML = `
        <div class="kpi-row">
            <span class="kpi-label" data-en="Today's Revenue" data-ja="本日売上">Today's Revenue</span>
            <span class="kpi-value">${fmt(today_revenue)}</span>
            <span class="kpi-diff neutral">${today_orders} orders</span>
        </div>
        <div class="kpi-row">
            <span class="kpi-label" data-en="Daily Avg (this month)" data-ja="日次平均（今月）">Daily Avg</span>
            <span class="kpi-value">${fmt(daily_avg)}</span>
            <span class="kpi-diff neutral">/ day</span>
        </div>
        <div class="kpi-row">
            <span class="kpi-label" data-en="vs Last Month Same Day" data-ja="前月同日比">vs Last Month</span>
            <span class="kpi-value">${sign}${fmt(revenue_diff)} ${arrow}</span>
            <span class="kpi-diff ${diffCls}">${sign}${revenue_diff_pct}%</span>
        </div>
    `;
}

/* ── 30-Day Chart (moved from inline) ── */
async function loadChart() {
    try {
        const data  = await apiFetch('/api/sales/analytics?days=30');
        const trend = data.daily_trend || [];
        const el    = document.getElementById('revenueChart');
        if (!el) return;
        if (trend.length === 0) {
            el.innerHTML = `<div class="empty-state">${t('No sales data yet.','売上データがありません。')}</div>`;
            return;
        }
        const options = {
            chart: {
                type: 'area', height: 220,
                fontFamily: 'Inter, sans-serif',
                toolbar: { show: false }, zoom: { enabled: false },
            },
            colors: ['#007AFF', '#34C759'],
            series: [
                { name: t('Revenue ($)', '売上($)'), data: trend.map(d => d.revenue_usd) },
                { name: t('Profit ($)', '利益($)'),  data: trend.map(d => d.profit_usd) },
            ],
            xaxis: {
                categories: trend.map(d => d.date.slice(5)),
                axisBorder: { show: false }, axisTicks: { show: false },
                labels: { style: { colors: '#9CA3AF', fontSize: '11px' } },
            },
            yaxis: { labels: { style: { colors: '#9CA3AF', fontSize: '11px' } } },
            grid: { borderColor: '#E5E7EB', xaxis: { lines: { show: false } } },
            stroke: { curve: 'straight', width: 2 },
            fill: { type: 'gradient', gradient: { opacityFrom: 0.45, opacityTo: 0 } },
            dataLabels: { enabled: false },
            legend: {
                position: 'top', horizontalAlign: 'left',
                fontFamily: 'Inter, sans-serif', fontSize: '13px',
                labels: { colors: '#9CA3AF' }, markers: { radius: 99 },
            },
            tooltip: { theme: 'light', style: { fontFamily: 'Inter, sans-serif' } },
        };
        new ApexCharts(el, options).render();
    } catch (e) {
        const el = document.getElementById('revenueChart');
        if (el) el.innerHTML = '<div class="empty-state">Could not load chart</div>';
    }
}

/* ── Activity Feed ── */
async function loadActivity() {
    try {
        const activities = await apiFetch('/api/activity/recent?limit=8');
        const container = document.getElementById('activityFeed');
        if (!container) return;
        if (!activities.length) {
            container.innerHTML = `<div class="empty-state">${t('No recent activity','最近のアクティビティはありません')}</div>`;
            return;
        }
        container.innerHTML = activities.map(a => `
            <div class="activity-item">
                <span class="activity-icon">${a.type === 'sale' ? '💰' : '🔧'}</span>
                <div>
                    <div class="activity-text">${escapeHtml(a.text)}</div>
                    <div class="activity-time">${formatDateTime(a.time)}</div>
                </div>
            </div>
        `).join('');
    } catch (e) {
        const el = document.getElementById('activityFeed');
        if (el) el.innerHTML = '<div class="empty-state">Could not load activity</div>';
    }
}

/* ── Entry Point ── */
async function initOverview() {
    await Promise.all([
        loadAlerts(),
        loadAchievement(),
        loadCalendar(),
        loadPace(),
        loadChart(),
        loadActivity(),
    ]);
}

initOverview();
```

- [ ] **Step 2: Commit**

```bash
git add products/ebay-agent/static/js/overview.js
git commit -m "feat: add overview.js (achievement, calendar, alerts, pace, chart)"
```

---

## Task 7: templates/pages/overview.html — レイアウト全面刷新

**Files:**
- Modify: `products/ebay-agent/templates/pages/overview.html`

- [ ] **Step 1: overview.html を新レイアウトに書き換える**

`products/ebay-agent/templates/pages/overview.html` 全体を以下で置き換え：

```html
{% extends "base.html" %}
{% block title %}Overview — eBay Agent Hub{% endblock %}
{% block breadcrumb %}Overview{% endblock %}
{% block page_title %}<span data-en="Overview" data-ja="概要">Overview</span>{% endblock %}

{% block head %}
<script src="https://cdn.jsdelivr.net/npm/apexcharts@3.49.0/dist/apexcharts.min.js"></script>
{% endblock %}

{% block content %}

<!-- ① Alert Strip -->
<div id="alertStrip" class="alert-strip" style="display:none"></div>

<!-- ② Achievement Board -->
<div class="achievement-board">

  <!-- Revenue Card -->
  <div class="achievement-card">
    <div class="ach-label" data-en="Monthly Revenue" data-ja="月間売上">Monthly Revenue</div>
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

  <!-- Profit Margin Card -->
  <div class="achievement-card">
    <div class="ach-label" data-en="Profit Margin" data-ja="利益率">Profit Margin</div>
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

  <!-- Profit Card -->
  <div class="achievement-card">
    <div class="ach-label" data-en="Monthly Profit" data-ja="月間利益">Monthly Profit</div>
    <div class="ach-values">
      <span class="ach-actual" id="profitActual">¥—</span>
      <span class="ach-target">/ ¥1,000,000</span>
    </div>
    <div class="progress-wrap">
      <div class="progress-bar" id="profitBar" style="width:0%"></div>
    </div>
    <div class="ach-meta">
      <span class="ach-rate" id="profitRate">—%</span>
      <span class="ach-pace" id="profitPace"></span>
    </div>
  </div>

</div>

<!-- ③ KPI Comparison + Calendar -->
<div class="overview-main-grid">

  <!-- KPI vs Last Month -->
  <div class="section">
    <h2 data-en="vs Last Month (Same Day)" data-ja="前月同日比">vs Last Month (Same Day)</h2>
    <div id="kpiTable" style="margin-top:12px">
      <div class="empty-state">Loading...</div>
    </div>
  </div>

  <!-- Sales Calendar -->
  <div class="section">
    <h2 id="calendarTitle">Sales Calendar</h2>
    <div id="salesCalendar" style="margin-top:12px">
      <div class="empty-state">Loading...</div>
    </div>
  </div>

</div>

<!-- ④ 30-Day Trend Chart -->
<div class="section" style="margin-bottom:20px">
  <h2 data-en="30-Day Revenue & Profit" data-ja="30日間の売上・利益">30-Day Revenue & Profit</h2>
  <div class="chart-container" style="margin-top:12px">
    <div id="revenueChart"></div>
  </div>
</div>

<!-- ⑤ Existing KPI Cards (detail) -->
<div class="stats-grid">
  <div class="stat-card">
    <div class="stat-icon blue">
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" d="m20.25 7.5-.625 10.632a2.25 2.25 0 0 1-2.247 2.118H6.622a2.25 2.25 0 0 1-2.247-2.118L3.75 7.5M10 11.25h4M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125Z" />
      </svg>
    </div>
    <div class="stat-content">
      <div class="label" data-en="Total Listings" data-ja="総出品数">Total Listings</div>
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
      <div class="label" data-en="In Stock" data-ja="在庫あり">In Stock</div>
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
      <div class="label" data-en="Out of Stock" data-ja="在庫切れ">Out of Stock</div>
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
      <div class="label" data-en="Source Candidates" data-ja="仕入れ候補">Source Candidates</div>
      <div class="value">{{ stats.source_candidates }}</div>
    </div>
  </div>
  <div class="stat-card">
    <div class="stat-icon purple">
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" d="M10.5 6h9.75M10.5 6a1.5 1.5 0 1 1-3 0m3 0a1.5 1.5 0 1 0-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 0 1-3 0m3 0a1.5 1.5 0 0 0-3 0m-9.75 0h9.75" />
      </svg>
    </div>
    <div class="stat-content">
      <div class="label" data-en="Pending Procurement" data-ja="調達中">Pending Procurement</div>
      <div class="value">{{ stats.pending_procurements }}</div>
    </div>
  </div>
  <div class="stat-card">
    <div class="stat-icon green">
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" d="M2.25 18.75a60.07 60.07 0 0 1 15.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 0 1 3 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 0 0-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 0 1-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 0 0 3 15h-.75M15 10.5a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm3 0h.008v.008H18V10.5Zm-12 0h.008v.008H6V10.5Z" />
      </svg>
    </div>
    <div class="stat-content">
      <div class="label" data-en="30d Revenue" data-ja="30日売上">30d Revenue</div>
      <div class="value">${{ "%.0f"|format(stats.sales_30d.total_revenue_usd) }}</div>
      <div class="sub">Profit: ${{ "%.0f"|format(stats.sales_30d.total_profit_usd) }} ({{ stats.sales_30d.total_sales }} sales)</div>
    </div>
  </div>
  {% if stats.inventory and (stats.inventory.in_stock + stats.inventory.listed) > 0 %}
  <div class="stat-card">
    <div class="stat-icon blue">
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" d="M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5M10 11.25h4M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z" />
      </svg>
    </div>
    <div class="stat-content">
      <div class="label" data-en="Physical Stock" data-ja="有在庫">Physical Stock</div>
      <div class="value">{{ stats.inventory.in_stock + stats.inventory.listed }}</div>
      <div class="sub">¥{{ "{:,}".format(stats.inventory.stock_value_jpy) }} · {{ stats.inventory.avg_days_in_stock }}d avg</div>
    </div>
  </div>
  {% endif %}
</div>

<!-- ⑥ Recent Activity -->
<div class="section">
  <h2 data-en="Recent Activity" data-ja="最近のアクティビティ">Recent Activity</h2>
  <div id="activityFeed" style="margin-top:12px">
    <div class="empty-state">Loading...</div>
  </div>
</div>

{% endblock %}

{% block scripts %}
<script src="/static/js/overview.js"></script>
{% endblock %}
```

- [ ] **Step 2: ブラウザで Overview を開いて動作確認**

```bash
open http://localhost:8000/
```

確認チェックリスト：
- [ ] アラートストリップが表示される（または在庫切れ0件なら非表示）
- [ ] 達成ボード3カードが横並びで表示される
- [ ] プログレスバーが幅0%でも表示が崩れない
- [ ] カレンダーが7列グリッドで表示される
- [ ] 既存の KPI カード（stat-card）が下部に表示される
- [ ] ApexCharts トレンドチャートが表示される
- [ ] コンソールエラーが出ない（F12 → Console）

- [ ] **Step 3: Commit**

```bash
git add products/ebay-agent/templates/pages/overview.html
git commit -m "feat: redesign overview page with achievement board, calendar, alert strip"
```

---

## Task 8: 最終統合確認

- [ ] **Step 1: サーバーを再起動して全体動作確認**

```bash
pkill -f uvicorn; sleep 1
cd products/ebay-agent
uvicorn main:app --reload --port 8000
```

- [ ] **Step 2: 全 API エンドポイントの最終確認**

```bash
for ep in achievement calendar alerts pace; do
  echo "=== /api/overview/$ep ==="
  curl -s "http://localhost:8000/api/overview/$ep" | python -m json.tool
done
```

- [ ] **Step 3: テスト最終実行**

```bash
cd products/ebay-agent
pytest tests/test_overview_crud.py -v
```

全5テスト PASSED を確認。

- [ ] **Step 4: 最終 Commit & Push**

```bash
git add -u
git commit -m "feat: eBay Agent Hub dashboard redesign complete

- Achievement board: monthly revenue/margin/profit vs targets
- Alert strip: OOS / unread / price alert counts
- Sales calendar heatmap: daily revenue visualization
- Pace projection: month-end forecast + vs last month
- overview.js: extracted from inline + new features
- 4 new /api/overview/* endpoints

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin feature/video-ad-generator
```

---

## Self-Review

**Spec coverage check:**
- ✅ アラートストリップ → Task 5(CSS) + Task 6(JS `renderAlerts`) + Task 7(HTML)
- ✅ 達成ボード3カラム（¥5M/20%/¥1M）→ Task 1(定数) + Task 2(CRUD) + Task 4(API) + Task 6(JS) + Task 7(HTML)
- ✅ ペース予測 → `get_monthly_achievement` の `projected_eom`
- ✅ KPI前月同日比 → Task 2 `get_overview_pace` + Task 6 `renderPace`
- ✅ カレンダーヒートマップ → Task 2 `get_monthly_calendar` + Task 6 `renderCalendar`
- ✅ 30日グラフ（既存維持）→ Task 6 `loadChart`
- ✅ スキーマ変更なし → 新テーブル追加なし

**Placeholder scan:** TBD/TODO なし ✅

**型整合性:**
- `get_monthly_achievement` → `revenue.actual`, `profit.actual`, `profit_margin.actual` → `renderAchievement` で `fmt(rev.actual)`, `pct(margin.actual)` と一致 ✅
- `get_monthly_calendar` → `{ year, month, days: [{date, revenue, orders, profit}] }` → `renderCalendar(data)` の `data.year, data.month, data.days` と一致 ✅
- `get_overview_alerts` → `{ out_of_stock, unread_messages, price_alerts, severity }` → `renderAlerts(data)` と一致 ✅
- `get_overview_pace` → `{ today_revenue, today_orders, daily_avg, prev_month_comparison: { revenue_diff, revenue_diff_pct } }` → `renderPace(data)` と一致 ✅
