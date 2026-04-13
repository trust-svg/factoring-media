import sqlite3
import json
import os
from datetime import datetime
from typing import Optional

DB_PATH = os.getenv("DB_PATH", "simulator.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(
    initial_capital: float = 10000.0,
    jp_alloc: float = 0.5,
    us_alloc: float = 0.5,
) -> None:
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS portfolio (
            id INTEGER PRIMARY KEY,
            cash_jp REAL NOT NULL,
            cash_us REAL NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL UNIQUE,
            market TEXT NOT NULL,
            shares INTEGER NOT NULL,
            avg_cost REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            market TEXT NOT NULL,
            action TEXT NOT NULL,
            shares INTEGER,
            price REAL,
            reason TEXT,
            pnl REAL,
            executed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            total_value REAL NOT NULL,
            recorded_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cycle_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            market TEXT NOT NULL,
            input_text TEXT NOT NULL,
            decisions_json TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        );
    """)
    existing = conn.execute("SELECT COUNT(*) FROM portfolio").fetchone()[0]
    if existing == 0:
        conn.execute(
            "INSERT INTO portfolio (id, cash_jp, cash_us, updated_at) VALUES (1, ?, ?, ?)",
            (initial_capital * jp_alloc, initial_capital * us_alloc, datetime.now().isoformat()),
        )
    conn.commit()
    conn.close()


def get_portfolio() -> dict:
    conn = get_conn()
    row = conn.execute("SELECT * FROM portfolio WHERE id = 1").fetchone()
    conn.close()
    return dict(row)


def update_cash(market: str, delta: float) -> None:
    field = "cash_jp" if market == "JP" else "cash_us"
    conn = get_conn()
    conn.execute(
        f"UPDATE portfolio SET {field} = {field} + ?, updated_at = ? WHERE id = 1",
        (delta, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_positions() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM positions").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_position(ticker: str) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM positions WHERE ticker = ?", (ticker,)).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_position(ticker: str, market: str, shares: int, avg_cost: float) -> None:
    conn = get_conn()
    existing = conn.execute("SELECT * FROM positions WHERE ticker = ?", (ticker,)).fetchone()
    if existing:
        new_shares = existing["shares"] + shares
        new_cost = (existing["avg_cost"] * existing["shares"] + avg_cost * shares) / new_shares
        conn.execute(
            "UPDATE positions SET shares = ?, avg_cost = ? WHERE ticker = ?",
            (new_shares, new_cost, ticker),
        )
    else:
        conn.execute(
            "INSERT INTO positions (ticker, market, shares, avg_cost) VALUES (?, ?, ?, ?)",
            (ticker, market, shares, avg_cost),
        )
    conn.commit()
    conn.close()


def reduce_position(ticker: str, shares: int) -> bool:
    conn = get_conn()
    existing = conn.execute("SELECT * FROM positions WHERE ticker = ?", (ticker,)).fetchone()
    if not existing or existing["shares"] < shares:
        conn.close()
        return False
    new_shares = existing["shares"] - shares
    if new_shares == 0:
        conn.execute("DELETE FROM positions WHERE ticker = ?", (ticker,))
    else:
        conn.execute("UPDATE positions SET shares = ? WHERE ticker = ?", (new_shares, ticker))
    conn.commit()
    conn.close()
    return True


def record_trade(
    ticker: str,
    market: str,
    action: str,
    shares: Optional[int],
    price: Optional[float],
    reason: str,
    pnl: Optional[float] = None,
) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO trades (ticker, market, action, shares, price, reason, pnl, executed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (ticker, market, action, shares, price, reason, pnl, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_trades(limit: int = 50) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM trades ORDER BY executed_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_trades_paginated(limit: int = 20, offset: int = 0) -> dict:
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    rows = conn.execute(
        "SELECT * FROM trades ORDER BY executed_at DESC LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()
    conn.close()
    return {"total": total, "items": [dict(r) for r in rows]}


def get_trades_since(days: int = 7) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM trades WHERE executed_at >= datetime('now', ? || ' days') "
        "ORDER BY executed_at DESC",
        (f"-{days}",),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def record_snapshot(total_value: float) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO snapshots (total_value, recorded_at) VALUES (?, ?)",
        (total_value, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_snapshots(limit: int = 100) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM snapshots ORDER BY recorded_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def record_cycle_log(log: dict) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO cycle_logs (timestamp, market, input_text, decisions_json, recorded_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            log["timestamp"],
            log["market"],
            log["input"],
            json.dumps(log["decisions"], ensure_ascii=False),
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_cycle_logs(limit: int = 30) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM cycle_logs ORDER BY recorded_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [
        {
            "timestamp": r["timestamp"],
            "market": r["market"],
            "input": r["input_text"],
            "decisions": json.loads(r["decisions_json"]),
        }
        for r in rows
    ]


def reset_db(
    initial_capital: float = 10000.0,
    jp_alloc: float = 0.5,
    us_alloc: float = 0.5,
) -> None:
    conn = get_conn()
    conn.executescript("""
        DELETE FROM portfolio;
        DELETE FROM positions;
        DELETE FROM trades;
        DELETE FROM snapshots;
        DELETE FROM cycle_logs;
    """)
    conn.execute(
        "INSERT INTO portfolio (id, cash_jp, cash_us, updated_at) VALUES (1, ?, ?, ?)",
        (initial_capital * jp_alloc, initial_capital * us_alloc, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
