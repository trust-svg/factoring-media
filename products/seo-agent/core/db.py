from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS rank_history (
    site TEXT NOT NULL,
    date TEXT NOT NULL,
    keyword TEXT NOT NULL,
    page TEXT NOT NULL,
    impressions INTEGER NOT NULL,
    clicks INTEGER NOT NULL,
    ctr REAL NOT NULL,
    position REAL NOT NULL,
    PRIMARY KEY (site, date, keyword, page)
);

CREATE INDEX IF NOT EXISTS idx_rank_history_site_kw ON rank_history(site, keyword);
CREATE INDEX IF NOT EXISTS idx_rank_history_site_date ON rank_history(site, date);

CREATE TABLE IF NOT EXISTS report_runs (
    site TEXT NOT NULL,
    run_date TEXT NOT NULL,
    rows_written INTEGER NOT NULL,
    report_path TEXT,
    PRIMARY KEY (site, run_date)
);
"""


def db_path() -> Path:
    return Path(os.getenv("DB_PATH", "/app/data/seo.db"))


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_schema() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def upsert_rows(site: str, date: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    with connect() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO rank_history
            (site, date, keyword, page, impressions, clicks, ctr, position)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    site,
                    date,
                    r["keyword"],
                    r["page"],
                    int(r["impressions"]),
                    int(r["clicks"]),
                    float(r["ctr"]),
                    float(r["position"]),
                )
                for r in rows
            ],
        )
    return len(rows)


def fetch_previous_position(site: str, keyword: str, page: str, before_date: str) -> float | None:
    with connect() as conn:
        cur = conn.execute(
            """
            SELECT position FROM rank_history
            WHERE site = ? AND keyword = ? AND page = ? AND date < ?
            ORDER BY date DESC LIMIT 1
            """,
            (site, keyword, page, before_date),
        )
        row = cur.fetchone()
        return float(row["position"]) if row else None


def record_run(site: str, run_date: str, rows_written: int, report_path: str | None) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO report_runs (site, run_date, rows_written, report_path)
            VALUES (?, ?, ?, ?)
            """,
            (site, run_date, rows_written, report_path),
        )
