"""知見エンジンの永続化（SQLite WAL + FTS5 trigram）。

フェーズ1: digests テーブル（チャンネル×日付ごとの構造化議事録）。
SQLite が正データ。Markdown ビューは knowledge/views.py が別途書き出す。
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Optional


def _now_iso(now: Optional[dt.datetime] = None) -> str:
    return (now or dt.datetime.now()).strftime("%Y-%m-%dT%H:%M:%S")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS digests (
    id              INTEGER PRIMARY KEY,
    channel_id      TEXT NOT NULL,
    channel_name    TEXT,
    department      TEXT,
    date            TEXT NOT NULL,
    source_kind     TEXT NOT NULL,
    turn_count      INTEGER NOT NULL DEFAULT 0,
    summary_md      TEXT NOT NULL,
    topics_json     TEXT,
    decisions_json  TEXT,
    open_items_json TEXT,
    next_actions_json TEXT,
    facts_json      TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE(channel_id, date)
);
CREATE INDEX IF NOT EXISTS idx_digests_date ON digests(date);
"""

_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS digests_fts USING fts5(
    summary_md, topics, content='', tokenize='trigram'
);
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(db_path: Path) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    try:
        conn.executescript(_SCHEMA)
        try:
            conn.executescript(_FTS_SCHEMA)
        except sqlite3.OperationalError:
            # FTS5/trigram 非対応ビルドのときは検索を諦める（get/upsert は動く）
            pass
        conn.commit()
    finally:
        conn.close()


def _dump(v) -> Optional[str]:
    return None if v is None else json.dumps(v, ensure_ascii=False)


def upsert_digest(
    db_path: Path,
    *,
    channel_id: str,
    channel_name: Optional[str],
    department: Optional[str],
    date: str,
    source_kind: str,
    turn_count: int,
    summary_md: str,
    topics: Optional[list] = None,
    decisions: Optional[list] = None,
    open_items: Optional[list] = None,
    next_actions: Optional[list] = None,
    facts: Optional[list] = None,
    now: Optional[dt.datetime] = None,
) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO digests(channel_id, channel_name, department, date, source_kind, "
            "turn_count, summary_md, topics_json, decisions_json, open_items_json, "
            "next_actions_json, facts_json, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(channel_id, date) DO UPDATE SET "
            "channel_name=excluded.channel_name, department=excluded.department, "
            "source_kind=excluded.source_kind, turn_count=excluded.turn_count, "
            "summary_md=excluded.summary_md, topics_json=excluded.topics_json, "
            "decisions_json=excluded.decisions_json, open_items_json=excluded.open_items_json, "
            "next_actions_json=excluded.next_actions_json, facts_json=excluded.facts_json, "
            "created_at=excluded.created_at",
            (
                channel_id,
                channel_name,
                department,
                date,
                source_kind,
                turn_count,
                summary_md,
                _dump(topics),
                _dump(decisions),
                _dump(open_items),
                _dump(next_actions),
                _dump(facts),
                _now_iso(now),
            ),
        )
        # FTS は content='' の外部コンテンツ無しなので、行ごとに delete→insert で更新する
        try:
            conn.execute(
                "DELETE FROM digests_fts WHERE rowid = "
                "(SELECT id FROM digests WHERE channel_id=? AND date=?)",
                (channel_id, date),
            )
            conn.execute(
                "INSERT INTO digests_fts(rowid, summary_md, topics) "
                "SELECT id, summary_md, COALESCE(topics_json, '') FROM digests WHERE channel_id=? AND date=?",
                (channel_id, date),
            )
        except sqlite3.OperationalError:
            pass
        conn.commit()
    finally:
        conn.close()


def get_digests(db_path: Path, date: str) -> list:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM digests WHERE date=? ORDER BY department, channel_name",
            (date,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _like_search(conn: sqlite3.Connection, query: str, limit: int) -> list:
    # LIKE のワイルドカード（% _）はエスケープしてリテラル扱いにする
    esc = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    like = f"%{esc}%"
    rows = conn.execute(
        "SELECT * FROM digests WHERE summary_md LIKE ? ESCAPE '\\' "
        "OR COALESCE(topics_json,'') LIKE ? ESCAPE '\\' ORDER BY date DESC LIMIT ?",
        (like, like, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def search(db_path: Path, query: str, limit: int = 50) -> list:
    """議事録の全文検索。3文字以上は FTS5 trigram、2文字以下は LIKE フォールバック。

    `!digest` コマンドや将来のコンサルモードから任意文字列が渡るので、FTS5 構文エラーや
    trigram 非対応ビルドは捕まえて LIKE フォールバックに落とす。
    """
    query = (query or "").strip()
    if not query:
        return []
    conn = _connect(db_path)
    try:
        rows = None
        if len(query) >= 3:
            try:
                rows = conn.execute(
                    "SELECT d.* FROM digests_fts f JOIN digests d ON d.id=f.rowid "
                    "WHERE digests_fts MATCH ? ORDER BY d.date DESC LIMIT ?",
                    (query, limit),
                ).fetchall()
                rows = [dict(r) for r in rows]
            except sqlite3.OperationalError:
                rows = None  # FTS5 構文エラー / trigram 非対応 → LIKE
        if rows is None:
            rows = _like_search(conn, query, limit)
        return rows
    finally:
        conn.close()
