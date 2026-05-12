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
        # init_db を呼ばずに record_turn だけ使われても安全に動くようスキーマを保証する。
        # ただし executescript は暗黙 COMMIT を伴うので、毎回ではなくテーブル不在時のみ実行する。
        has_turns = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='turns'"
        ).fetchone()
        if not has_turns:
            conn.executescript(_SCHEMA)
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


def list_pending_reviews(
    db_path: Path,
    today: Optional[dt.date] = None,
    min_turns: int = 2,
    max_age_days: int = 2,
) -> list[dict]:
    """未レビューで、活動日が今日より前、max_age_days 以内、reviewable、ターン数充足のセッション。"""
    today = today or dt.date.today()
    oldest = (today - dt.timedelta(days=max_age_days)).strftime("%Y-%m-%d")
    cutoff_today = today.strftime("%Y-%m-%d")
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE review_status IS NULL AND reviewable=1 "
            "AND review_date < ? AND review_date >= ? AND turn_count >= ? "
            "ORDER BY review_date, channel_id",
            (cutoff_today, oldest, min_turns),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_sessions_for_date(db_path: Path, date: str, min_turns: int = 1) -> list[dict]:
    """指定日のセッション（チャンネル）一覧。レビュー状態は問わない。turn_count >= min_turns のみ。"""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE review_date=? AND turn_count >= ? "
            "ORDER BY channel_id",
            (date, min_turns),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_review_start(
    db_path: Path,
    channel_id: str,
    review_date: str,
    now: Optional[dt.datetime] = None,
) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            "UPDATE sessions SET review_status='running', review_started_at=? "
            "WHERE channel_id=? AND review_date=?",
            (_now_iso(now), channel_id, review_date),
        )
        conn.commit()
    finally:
        conn.close()


def mark_reviewed(
    db_path: Path,
    channel_id: str,
    review_date: str,
    status: str,
    note: str = "",
    now: Optional[dt.datetime] = None,
) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            "UPDATE sessions SET review_status=?, reviewed_at=?, review_note=?, review_started_at=NULL "
            "WHERE channel_id=? AND review_date=?",
            (status, _now_iso(now), note, channel_id, review_date),
        )
        conn.commit()
    finally:
        conn.close()


def requeue_stuck(
    db_path: Path,
    stuck_minutes: int = 30,
    now: Optional[dt.datetime] = None,
) -> int:
    """review_status='running' のまま stuck_minutes 超のものを NULL に戻す。戻した件数を返す。"""
    now = now or dt.datetime.now()
    threshold = (now - dt.timedelta(minutes=stuck_minutes)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "UPDATE sessions SET review_status=NULL, review_started_at=NULL "
            "WHERE review_status='running' AND review_started_at < ?",
            (threshold,),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def mark_short_skipped(
    db_path: Path,
    today: Optional[dt.date] = None,
    min_turns: int = 2,
) -> int:
    """ターン数不足で閉じた（=今日より前の）未レビュー reviewable セッションを skipped(too_short) に。"""
    today = today or dt.date.today()
    cutoff = today.strftime("%Y-%m-%d")
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "UPDATE sessions SET review_status='skipped', review_note='too_short' "
            "WHERE review_status IS NULL AND reviewable=1 AND review_date < ? AND turn_count < ?",
            (cutoff, min_turns),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def _like_query(conn: sqlite3.Connection, query: str, limit: int) -> list:
    # `%` `_` `\` はワイルドカードなのでエスケープ（ユーザー入力をそのまま LIKE に渡さない）。
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return conn.execute(
        "SELECT channel_name, department, ts, role, content, review_date "
        "FROM turns WHERE content LIKE ? ESCAPE '\\' ORDER BY ts DESC LIMIT ?",
        (f"%{escaped}%", limit),
    ).fetchall()


def search(db_path: Path, query: str, limit: int = 50) -> list[dict]:
    """会話ログ全文検索。3文字以上は FTS5 trigram、2文字以下は LIKE フォールバック。

    Discord メッセージ由来の任意文字列が渡るので、FTS5 構文エラー（未閉じ引用符・
    NOT/OR で終わる等）は捕まえて LIKE フォールバックに落とす。
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
                    "SELECT t.channel_name, t.department, t.ts, t.role, t.content, t.review_date "
                    "FROM turns_fts f JOIN turns t ON t.id = f.rowid "
                    "WHERE turns_fts MATCH ? ORDER BY t.ts DESC LIMIT ?",
                    (query, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = None  # FTS5 構文エラー → LIKE フォールバック
        if rows is None:
            rows = _like_query(conn, query, limit)
        return [dict(r) for r in rows]
    finally:
        conn.close()


def prune(
    db_path: Path,
    retention_days: int = 180,
    now: Optional[dt.datetime] = None,
) -> int:
    """ts が retention_days より古い turns を削除（turns_fts はトリガで連動）。削除件数を返す。sessions 台帳は残す。"""
    now = now or dt.datetime.now()
    cutoff = (now - dt.timedelta(days=retention_days)).strftime("%Y-%m-%dT%H:%M:%S")
    conn = _connect(db_path)
    try:
        cur = conn.execute("DELETE FROM turns WHERE ts < ?", (cutoff,))
        conn.commit()
        conn.execute("INSERT INTO turns_fts(turns_fts) VALUES('optimize')")
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def skill_metrics(skills_dir: Path) -> dict:
    """`.company/skills/` の規模を計測（肥大メトリクス用）。

    count: トップレベル `<name>.md` と `<name>/SKILL.md` の合計件数。
    concat_chars: それらを system prompt に連結したときの本文文字数合計（references/ は含めない）。
    """
    skills_dir = Path(skills_dir)
    count = 0
    concat_chars = 0
    if not skills_dir.exists():
        return {"count": 0, "concat_chars": 0}

    def _len(p: Path) -> int:
        try:
            return len(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            return 0  # 読めないファイルはメトリクスではスキップ（監視用途なので落とさない）

    for entry in sorted(skills_dir.iterdir()):
        if entry.name.startswith("."):
            continue  # .archive / .snapshots を除外
        if entry.is_file() and entry.suffix == ".md":
            count += 1
            concat_chars += _len(entry)
        elif entry.is_dir():
            skill_md = entry / "SKILL.md"
            if skill_md.exists():
                count += 1
                concat_chars += _len(skill_md)
    return {"count": count, "concat_chars": concat_chars}
