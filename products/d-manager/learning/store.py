"""学習ループの会話ログ永続化（SQLite WAL + FTS5 trigram）。

「セッション」= (channel_id, review_date) で定義する（CLI セッションの 12h アイドル境界には依存しない）。
turns: 1ターン = ユーザー1発言 or エージェント1応答。
sessions: レビュー台帳（キー = (channel_id, review_date)）。
turns_fts: 日本語部分一致検索（trigram, クエリ3文字以上で有効）。
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Optional


def _now_iso(now: Optional[dt.datetime] = None) -> str:
    return (now or dt.datetime.now()).strftime("%Y-%m-%dT%H:%M:%S")


def _review_date(now: Optional[dt.datetime] = None) -> str:
    return (now or dt.datetime.now()).strftime("%Y-%m-%d")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id            INTEGER PRIMARY KEY,
    channel_id    TEXT NOT NULL,
    channel_name  TEXT,
    department    TEXT,
    cli_session_id TEXT,
    review_date   TEXT NOT NULL,
    turn_idx      INTEGER NOT NULL,
    role          TEXT NOT NULL,
    content       TEXT NOT NULL,
    engine        TEXT NOT NULL,
    origin        TEXT NOT NULL,
    ts            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turns_chan_date ON turns(channel_id, review_date, turn_idx);
CREATE INDEX IF NOT EXISTS idx_turns_ts ON turns(ts);

CREATE TABLE IF NOT EXISTS sessions (
    channel_id    TEXT NOT NULL,
    review_date   TEXT NOT NULL,
    channel_name  TEXT,
    department    TEXT,
    origin        TEXT NOT NULL,
    first_turn_at TEXT NOT NULL,
    last_turn_at  TEXT NOT NULL,
    turn_count    INTEGER NOT NULL DEFAULT 0,
    reviewable    INTEGER NOT NULL DEFAULT 1,
    review_status TEXT,
    review_started_at TEXT,
    reviewed_at   TEXT,
    review_note   TEXT,
    PRIMARY KEY (channel_id, review_date)
);

CREATE VIRTUAL TABLE IF NOT EXISTS turns_fts USING fts5(
    content, content='turns', content_rowid='id', tokenize='trigram'
);

CREATE TRIGGER IF NOT EXISTS turns_ai AFTER INSERT ON turns BEGIN
    INSERT INTO turns_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS turns_ad AFTER DELETE ON turns BEGIN
    INSERT INTO turns_fts(turns_fts, rowid, content) VALUES('delete', old.id, old.content);
END;
CREATE TRIGGER IF NOT EXISTS turns_au AFTER UPDATE ON turns BEGIN
    INSERT INTO turns_fts(turns_fts, rowid, content) VALUES('delete', old.id, old.content);
    INSERT INTO turns_fts(rowid, content) VALUES (new.id, new.content);
END;
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(db_path: Path) -> None:
    conn = _connect(db_path)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def record_turn(
    db_path: Path,
    channel_id: str,
    channel_name: Optional[str],
    department: Optional[str],
    cli_session_id: Optional[str],
    role: str,
    content: str,
    engine: str,
    origin: str = "chat",
    reviewable: bool = True,
    now: Optional[dt.datetime] = None,
) -> None:
    """1ターンを記録し、(channel_id, review_date) の sessions 行を upsert する。"""
    rdate = _review_date(now)
    ts = _now_iso(now)
    conn = _connect(db_path)
    try:
        conn.executescript(_SCHEMA)  # 冪等
        cur = conn.execute(
            "SELECT COALESCE(MAX(turn_idx), -1) AS m FROM turns WHERE channel_id=? AND review_date=?",
            (channel_id, rdate),
        )
        next_idx = cur.fetchone()["m"] + 1
        conn.execute(
            "INSERT INTO turns(channel_id, channel_name, department, cli_session_id, "
            "review_date, turn_idx, role, content, engine, origin, ts) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                channel_id,
                channel_name,
                department,
                cli_session_id,
                rdate,
                next_idx,
                role,
                content,
                engine,
                origin,
                ts,
            ),
        )
        existing = conn.execute(
            "SELECT 1 FROM sessions WHERE channel_id=? AND review_date=?",
            (channel_id, rdate),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE sessions SET last_turn_at=?, turn_count=turn_count+1 "
                "WHERE channel_id=? AND review_date=?",
                (ts, channel_id, rdate),
            )
        else:
            conn.execute(
                "INSERT INTO sessions(channel_id, review_date, channel_name, department, "
                "origin, first_turn_at, last_turn_at, turn_count, reviewable) "
                "VALUES (?,?,?,?,?,?,?,1,?)",
                (
                    channel_id,
                    rdate,
                    channel_name,
                    department,
                    origin,
                    ts,
                    ts,
                    1 if reviewable else 0,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def get_session_turns(db_path: Path, channel_id: str, review_date: str) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT turn_idx, role, content, ts, department, channel_name "
            "FROM turns WHERE channel_id=? AND review_date=? ORDER BY turn_idx, ts",
            (channel_id, review_date),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_session_row(db_path: Path, channel_id: str, review_date: str) -> Optional[dict]:
    conn = _connect(db_path)
    try:
        r = conn.execute(
            "SELECT * FROM sessions WHERE channel_id=? AND review_date=?",
            (channel_id, review_date),
        ).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()
