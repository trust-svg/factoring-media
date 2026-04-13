import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
import pytz

import db
import market as mkt
from scheduler import create_scheduler

load_dotenv()

_scheduler = None
_start_time: datetime | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler, _start_time
    db.init_db(
        initial_capital=float(os.getenv("INITIAL_CAPITAL", 10000)),
        jp_alloc=float(os.getenv("JP_ALLOCATION", 0.5)),
        us_alloc=float(os.getenv("US_ALLOCATION", 0.5)),
    )
    _scheduler = create_scheduler(int(os.getenv("CHECK_INTERVAL_MINUTES", 15)))
    _scheduler.start()
    _start_time = datetime.now(timezone.utc)
    yield
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()


app = FastAPI(title="投資シミュレーター", lifespan=lifespan)


@app.get("/api/portfolio")
def get_portfolio():
    portfolio = db.get_portfolio()
    positions = db.get_positions()
    usdjpy = mkt.get_usdjpy()
    prices = mkt.get_market_data([p["ticker"] for p in positions]) if positions else {}
    position_value = sum(
        prices.get(p["ticker"], p["avg_cost"]) * p["shares"] for p in positions
    )
    total = portfolio["cash_jp"] + portfolio["cash_us"] + position_value
    initial = float(os.getenv("INITIAL_CAPITAL", 10000))
    pnl = total - initial
    return {
        "cash_jp": portfolio["cash_jp"],
        "cash_us": portfolio["cash_us"],
        "position_value": position_value,
        "total_value": total,
        "pnl": pnl,
        "pnl_pct": (pnl / initial) * 100,
        "jp_market_open": mkt.is_jp_market_open(),
        "us_market_open": mkt.is_us_market_open(),
        "usdjpy": usdjpy,
    }


@app.get("/api/positions")
def get_positions():
    positions = db.get_positions()
    if not positions:
        return []
    prices = mkt.get_market_data([p["ticker"] for p in positions])
    return [
        {
            **p,
            "current_price": prices.get(p["ticker"], p["avg_cost"]),
            "current_value": prices.get(p["ticker"], p["avg_cost"]) * p["shares"],
            "pnl_pct": (prices.get(p["ticker"], p["avg_cost"]) / p["avg_cost"] - 1) * 100,
        }
        for p in positions
    ]


@app.get("/api/trades")
def get_trades(page: int = 1, limit: int = 20):
    offset = (page - 1) * limit
    data = db.get_trades_paginated(limit=limit, offset=offset)
    return {
        "items": data["items"],
        "total": data["total"],
        "page": page,
        "limit": limit,
        "pages": max(1, (data["total"] + limit - 1) // limit),
    }


@app.get("/api/snapshots")
def get_snapshots():
    return list(reversed(db.get_snapshots(100)))


@app.get("/api/status")
def get_status():
    jst = pytz.timezone("Asia/Tokyo")
    scheduler_running = _scheduler is not None and _scheduler.running

    next_jp = next_us = None
    if scheduler_running:
        jp_job = _scheduler.get_job("jp_cycle")
        us_job = _scheduler.get_job("us_cycle")
        if jp_job and jp_job.next_run_time:
            next_jp = jp_job.next_run_time.astimezone(jst).isoformat()
        if us_job and us_job.next_run_time:
            next_us = us_job.next_run_time.astimezone(jst).isoformat()

    trades = db.get_trades(200)
    last_jp = next((t["executed_at"] for t in trades if t["market"] == "JP"), None)
    last_us = next((t["executed_at"] for t in trades if t["market"] == "US"), None)

    uptime = int((datetime.now(timezone.utc) - _start_time).total_seconds()) if _start_time else 0

    return {
        "scheduler_running": scheduler_running,
        "next_jp_run": next_jp,
        "next_us_run": next_us,
        "last_jp_run": last_jp,
        "last_us_run": last_us,
        "uptime_seconds": uptime,
        "interval_minutes": int(os.getenv("CHECK_INTERVAL_MINUTES", 15)),
    }


class ManualTradeRequest(BaseModel):
    market: str  # "JP" or "US"


@app.get("/api/cycle_log")
def get_cycle_log():
    return db.get_cycle_logs(30)


@app.post("/api/trade/manual")
def manual_trade(req: ManualTradeRequest):
    import trader
    return trader.run_trading_cycle(req.market)


@app.post("/api/reset")
def reset():
    db.reset_db(
        initial_capital=float(os.getenv("INITIAL_CAPITAL", 10000)),
        jp_alloc=float(os.getenv("JP_ALLOCATION", 0.5)),
        us_alloc=float(os.getenv("US_ALLOCATION", 0.5)),
    )
    return {"status": "reset"}


# フロントエンド静的ファイル配信（最後にマウント）
frontend_path = os.path.join(os.path.dirname(__file__), "../frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="static")
