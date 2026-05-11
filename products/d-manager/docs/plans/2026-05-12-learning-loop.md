# d-manager 学習ループ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** d-manager に Hermes 流の自己改善ループを実装する — 会話を SQLite に永続化し、夜間バッチでセッション（=チャンネル+日付）を振り返って `.company/` 配下の skill / memory / rules を自動更新し、週次でスキルを棚卸しする。

**Architecture:** d-manager は通常 CLIモード（`claude -p` を `cwd=COMPANY_DIR` で叩く）で動く。学習ループも同じく `claude -p` をバックグラウンドで起動して `.company/` のファイルを書き換えさせる。会話ログは `products/d-manager/learning/conversations.db`（SQLite WAL + FTS5 trigram）。レビューの発火は夜間23:00のバッチが主、`!session reset` で即レビュー、フロー完了時に登録。週次キュレーターは既存 `weekly_review` ジョブに相乗り。レビュアー/キュレーターは Read/Write/Edit/Glob/Grep のみ（Bash・外部API禁止）、範囲外書き込みは `git checkout` で自動 revert。

**Tech Stack:** Python（`from __future__ import annotations` で型注釈を後方互換に保つ）、標準ライブラリ `sqlite3`（FTS5 trigram は SQLite 3.34+。本機では 3.53 確認済み）、`subprocess`（`claude -p` 起動）、`apscheduler`（既存 `AsyncIOScheduler`）、`discord.py`（既存）、`pytest`（テスト）。

**設計の出典:** `products/d-manager/docs/specs/2026-05-12-learning-loop-design.md`（コミット `f1b56ee` / `618a1c7`）。Hermes Agent（github.com/NousResearch/hermes-agent, MIT）の `_COMBINED_REVIEW_PROMPT` / `CURATOR_REVIEW_PROMPT` / "do NOT capture" ブロックリストをベースに移植する箇所には、ソースファイル先頭に `# Adapted from Hermes Agent (MIT) — github.com/NousResearch/hermes-agent` のコメントを必ず入れること。

**前提となるコードベースの事実（実装前に確認済み）:**
- `products/d-manager/ai_engine.py`: `_process_cli(user_message, department, channel_id) -> str`（正常系の `return result.stdout.strip()` が末尾付近にある）、`_process_api(user_message, department, channel_id) -> str`、`_get_or_create_cli_session(channel_id) -> tuple[str, bool]`、`reset_cli_session(channel_id) -> bool`、モジュール変数 `_cli_sessions: dict`。`process_message(user_message, department, channel_id)` が CLI/API を振り分ける。
- `products/d-manager/departments.py`: `load_department_prompt(department) -> str`（`.company/skills/*.md` を全部連結している箇所がある）、`get_department_for_channel(channel_name) -> str`。
- `products/d-manager/config.py`: モジュール末尾に定数を追記する。`config.COMPANY_DIR` は `Path`。
- `products/d-manager/scheduler.py`: `AsyncIOScheduler`、`async def weekly_review()`、末尾の `_scheduler.add_job(...)` 群。Discord 送信は既存ジョブが使っているヘルパ（`morning_briefing` 等がチャンネルに投稿している方法）に合わせる。
- `products/d-manager/main.py`: `on_message` 内で `raw = message.content.strip()` のあと `if raw.startswith("!rule"):` `if raw.startswith("!session"):` `if raw.startswith("!run"):` の分岐がある。`send_as_character_with_avatar(channel, text, channel_name)` / `send_to_channel(channel_name, text, view=None)` が使える。
- `products/d-manager/flows.py`: `async def run_flow(flow_name, args, send_fn, channel_override) -> Optional[str]`。末尾の `if ok:` ブロックでフロー完了。`_run_step` が `process_message` を `loop.run_in_executor` で呼ぶ。
- `products/d-manager/tests/` は**存在しない** → 作る。pytest 設定ファイルも無い → 必要なら `tests/conftest.py` だけ作る。

---

## ファイル構成

新規:
- `products/d-manager/learning/__init__.py` — 空（パッケージ化）
- `products/d-manager/learning/store.py` — SQLite ラッパ（スキーマ・`record_turn`・`get_session_turns`・`list_pending_reviews`・`mark_*`・`requeue_stuck`・`search`・`prune`・メトリクス集計）
- `products/d-manager/learning/reviewer.py` — `REVIEW_PROMPT` / レビュアー人格 / 会話ログ整形 / `run_review()`
- `products/d-manager/learning/curator.py` — `CURATOR_PROMPT` / キュレーター人格 / `run_curation()`
- `products/d-manager/learning/cli_runner.py` — `claude -p` をサブプロセス起動する薄いラッパ（reviewer/curator が共用）と `git_status_short` / `git_checkout` / `git_head` ヘルパ
- `products/d-manager/tests/__init__.py` — 空
- `products/d-manager/tests/conftest.py` — `sys.path` 調整（`products/d-manager/` をインポートルートに）
- `products/d-manager/tests/test_learning_store.py`
- `products/d-manager/tests/test_learning_reviewer.py`
- `products/d-manager/tests/test_learning_curator.py`
- `products/d-manager/tests/test_departments_loader.py`
- `products/d-manager/docs/plans/2026-05-12-learning-loop.md`（本書）

変更:
- `products/d-manager/config.py` — 学習ループ用定数
- `products/d-manager/ai_engine.py` — `_process_cli` / `_process_api` の正常終了直前に `store.record_turn` を2回。連続失敗カウンタ。
- `products/d-manager/departments.py` — `load_department_prompt` を `references/` デュアルローダー化 + `skills_concat_size()` 補助関数
- `products/d-manager/scheduler.py` — `learning_review` ジョブ追加（23:00）、`weekly_review` に `run_curation()` + `store.prune()` を追加、ジョブ例外ハンドラ
- `products/d-manager/main.py` — `!session reset` ハンドラから即レビューをキック、`!learning` コマンド群、`notify_learning_alert`
- （任意）`products/d-manager/flows.py` — `run_flow` 完了時のセッション登録。本プランでは省略（Task 14 のギャップ説明を参照）。フロー専用 synthetic channel を使っている場合のみ追加タスク化
- `.gitignore`（リポジトリルート） — `learning/*.db*` 等

---

## Task 1: config 定数の追加

**Files:**
- Modify: `products/d-manager/config.py`（末尾に追記）

- [ ] **Step 1: config.py の末尾に学習ループ用定数を追記**

`products/d-manager/config.py` の一番下に以下を追加する（`os` と `Path` は既に import 済み・`COMPANY_DIR` も定義済みの想定。無ければ既存の import に合わせる）:

```python
# ── Learning loop ─────────────────────────────────────────────────────────
LEARNING_DIR = Path(__file__).parent / "learning"
LEARNING_DB_PATH = Path(os.getenv("LEARNING_DB_PATH", str(LEARNING_DIR / "conversations.db")))
SKILL_HITS_PATH = LEARNING_DIR / "skill_hits.jsonl"

# Phase 1=観測のみ: ENABLED=false。Phase 2=ドライラン: ENABLED=true & DRYRUN=true。Phase 3=本番: 両方解除。
LEARNING_REVIEW_ENABLED = os.getenv("LEARNING_REVIEW_ENABLED", "false").lower() == "true"
LEARNING_REVIEW_DRYRUN = os.getenv("LEARNING_REVIEW_DRYRUN", "true").lower() == "true"

LEARNING_REVIEW_HOUR = int(os.getenv("LEARNING_REVIEW_HOUR", "23"))
LEARNING_MIN_TURNS = int(os.getenv("LEARNING_MIN_TURNS", "2"))
LEARNING_MAX_PER_RUN = int(os.getenv("LEARNING_MAX_PER_RUN", "3"))
LEARNING_REVIEW_MAX_AGE_DAYS = int(os.getenv("LEARNING_REVIEW_MAX_AGE_DAYS", "2"))
LEARNING_CONTEXT_CHAR_LIMIT = int(os.getenv("LEARNING_CONTEXT_CHAR_LIMIT", "40000"))
LEARNING_REVIEW_TIMEOUT_SEC = int(os.getenv("LEARNING_REVIEW_TIMEOUT_SEC", "300"))
LEARNING_CURATOR_TIMEOUT_SEC = int(os.getenv("LEARNING_CURATOR_TIMEOUT_SEC", "600"))
LEARNING_STUCK_MINUTES = int(os.getenv("LEARNING_STUCK_MINUTES", "30"))
TURNS_RETENTION_DAYS = int(os.getenv("TURNS_RETENTION_DAYS", "180"))

# レビュー/キュレーター用モデル（CLIモードの --model に渡す）。既定は日次=現行CLIモデル、週次=Opus。
REVIEW_MODEL_CLI = os.getenv("REVIEW_MODEL_CLI", CLAUDE_MODEL_CLI)
CURATOR_MODEL_CLI = os.getenv("CURATOR_MODEL_CLI", "claude-opus-4-7")

# 学習ループの通知先 Discord チャンネル名（既定: 開発チャンネル）
LEARNING_NOTIFY_CHANNEL = os.getenv("LEARNING_NOTIFY_CHANNEL", "開発-larry-product")

# スキル肥大アラートの閾値
SKILL_BLOAT_CHAR_THRESHOLD = int(os.getenv("SKILL_BLOAT_CHAR_THRESHOLD", "60000"))
SKILL_BLOAT_COUNT_THRESHOLD = int(os.getenv("SKILL_BLOAT_COUNT_THRESHOLD", "25"))

# レビュアー/キュレーターに渡すツール許可リスト（claude -p の --allowedTools / --disallowedTools）
LEARNING_ALLOWED_TOOLS = "Read Write Edit Glob Grep"
LEARNING_DRYRUN_ALLOWED_TOOLS = "Read Glob Grep"
LEARNING_DISALLOWED_TOOLS = "Bash WebFetch WebSearch Task"
```

注: `CLAUDE_MODEL_CLI` が config.py に既にあること（spec の前提）。無ければ `CLAUDE_MODEL` を使う。`CURATOR_MODEL_CLI` の既定値 `"claude-opus-4-7"` が現行 Opus のモデルIDで合っているか実装時に確認（合わなければ環境変数で上書きできるので致命的ではない）。

- [ ] **Step 2: import が通ることを確認**

Run: `cd products/d-manager && python -c "import config; print(config.LEARNING_DB_PATH, config.LEARNING_REVIEW_ENABLED, config.REVIEW_MODEL_CLI)"`
Expected: パスと `False` とモデルIDが表示され、例外なし。

- [ ] **Step 3: Commit**

```bash
git add products/d-manager/config.py
git commit -m "feat(d-manager): 学習ループ用 config 定数を追加"
```

---

## Task 2: learning パッケージと test 足場を作る

**Files:**
- Create: `products/d-manager/learning/__init__.py`
- Create: `products/d-manager/tests/__init__.py`
- Create: `products/d-manager/tests/conftest.py`
- Modify: `.gitignore`（リポジトリルート）

- [ ] **Step 1: 空のパッケージファイルを作る**

`products/d-manager/learning/__init__.py`:
```python
```
（完全に空でよい）

`products/d-manager/tests/__init__.py`:
```python
```
（完全に空でよい）

- [ ] **Step 2: conftest.py を作る**

`products/d-manager/tests/conftest.py`:
```python
"""pytest 共通設定: d-manager/ をインポートルートに加える。"""
from __future__ import annotations

import sys
from pathlib import Path

# tests/ の親（= products/d-manager/）を sys.path に追加し、`import config` 等を可能にする
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

- [ ] **Step 3: .gitignore に追記**

リポジトリルートの `.gitignore` の末尾に追加:
```
# d-manager learning loop (会話ログ・一時ファイルはコミットしない)
products/d-manager/learning/*.db
products/d-manager/learning/*.db-wal
products/d-manager/learning/*.db-shm
products/d-manager/learning/skill_hits.jsonl
.company/skills/.snapshots/
```

- [ ] **Step 4: pytest が起動できることを確認**

Run: `cd products/d-manager && python -m pytest tests/ -q`
Expected: `no tests ran`（テストファイルがまだ無いので 0 件。エラーなく終了すること）。`pytest` が無ければ `pip install pytest` してから。

- [ ] **Step 5: Commit**

```bash
git add products/d-manager/learning/__init__.py products/d-manager/tests/__init__.py products/d-manager/tests/conftest.py .gitignore
git commit -m "chore(d-manager): learning パッケージと pytest 足場・gitignore"
```

---

## Task 3: store.py — スキーマと record_turn / get_session_turns

**Files:**
- Create: `products/d-manager/learning/store.py`
- Create: `products/d-manager/tests/test_learning_store.py`

- [ ] **Step 1: 失敗するテストを書く**

`products/d-manager/tests/test_learning_store.py`:
```python
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from learning import store


@pytest.fixture
def db(tmp_path: Path):
    path = tmp_path / "test.db"
    store.init_db(path)
    return path


def _record(db_path, **over):
    base = dict(
        db_path=db_path,
        channel_id="chan-1",
        channel_name="運営-jack-operations",
        department="operations",
        cli_session_id="sess-abc",
        role="user",
        content="メルカリ仕入れの重複チェックどうやる？",
        engine="cli",
        origin="chat",
        reviewable=True,
        now=dt.datetime(2026, 5, 10, 9, 0, 0),
    )
    base.update(over)
    return store.record_turn(**base)


def test_record_and_get_session_turns(db):
    _record(db, role="user", content="質問1", now=dt.datetime(2026, 5, 10, 9, 0, 0))
    _record(db, role="assistant", content="回答1", now=dt.datetime(2026, 5, 10, 9, 0, 5))
    _record(db, role="user", content="質問2", now=dt.datetime(2026, 5, 10, 9, 1, 0))

    turns = store.get_session_turns(db, "chan-1", "2026-05-10")
    assert [t["role"] for t in turns] == ["user", "assistant", "user"]
    assert [t["content"] for t in turns] == ["質問1", "回答1", "質問2"]
    # turn_idx は (channel_id, review_date) 内の連番
    assert [t["turn_idx"] for t in turns] == [0, 1, 2]


def test_turn_idx_is_per_channel_date_not_per_session(db):
    _record(db, cli_session_id="sess-A", now=dt.datetime(2026, 5, 10, 9, 0, 0))
    _record(db, cli_session_id="sess-B", now=dt.datetime(2026, 5, 10, 20, 0, 0))
    turns = store.get_session_turns(db, "chan-1", "2026-05-10")
    assert [t["turn_idx"] for t in turns] == [0, 1]


def test_sessions_row_upserted(db):
    _record(db, now=dt.datetime(2026, 5, 10, 9, 0, 0))
    _record(db, now=dt.datetime(2026, 5, 10, 9, 5, 0))
    rows = store.get_session_row(db, "chan-1", "2026-05-10")
    assert rows["turn_count"] == 2
    assert rows["first_turn_at"].startswith("2026-05-10T09:00")
    assert rows["last_turn_at"].startswith("2026-05-10T09:05")
    assert rows["origin"] == "chat"
    assert rows["reviewable"] == 1
    assert rows["review_status"] is None
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `cd products/d-manager && python -m pytest tests/test_learning_store.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'learning.store'` または `AttributeError`）

- [ ] **Step 3: store.py を実装（スキーマ + record_turn + get_session_turns + get_session_row）**

`products/d-manager/learning/store.py`:
```python
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
            (channel_id, channel_name, department, cli_session_id, rdate, next_idx,
             role, content, engine, origin, ts),
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
                (channel_id, rdate, channel_name, department, origin, ts, ts,
                 1 if reviewable else 0),
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
```

- [ ] **Step 4: テストを実行して通ることを確認**

Run: `cd products/d-manager && python -m pytest tests/test_learning_store.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add products/d-manager/learning/store.py products/d-manager/tests/test_learning_store.py
git commit -m "feat(d-manager): learning store のスキーマ・record_turn・get_session_turns"
```

---

## Task 4: store.py — レビュー台帳の操作（list_pending_reviews / mark_* / requeue_stuck / mark_short_skipped）

**Files:**
- Modify: `products/d-manager/learning/store.py`
- Modify: `products/d-manager/tests/test_learning_store.py`

- [ ] **Step 1: 失敗するテストを追記**

`products/d-manager/tests/test_learning_store.py` の末尾に追加:
```python
def test_list_pending_reviews(db):
    # 前日のレビュー可能セッション → 対象になる
    _record(db, channel_id="c-old", now=dt.datetime(2026, 5, 10, 9, 0))
    _record(db, channel_id="c-old", now=dt.datetime(2026, 5, 10, 9, 5))
    # 当日（=today 扱い）のセッション → まだ活動が増えるかもしれないので対象外
    # 古すぎる（max_age_days 超）→ 対象外
    _record(db, channel_id="c-ancient", now=dt.datetime(2026, 4, 1, 9, 0))
    _record(db, channel_id="c-ancient", now=dt.datetime(2026, 4, 1, 9, 5))
    # reviewable=False → 対象外
    _record(db, channel_id="c-noreview", reviewable=False, now=dt.datetime(2026, 5, 10, 9, 0))
    _record(db, channel_id="c-noreview", reviewable=False, now=dt.datetime(2026, 5, 10, 9, 5))
    # ターン数不足（1ターンだけ）→ 対象外（mark_short_skipped 行き）
    _record(db, channel_id="c-short", now=dt.datetime(2026, 5, 10, 9, 0))

    pending = store.list_pending_reviews(
        db, today=dt.date(2026, 5, 11), min_turns=2, max_age_days=2
    )
    chans = {p["channel_id"] for p in pending}
    assert chans == {"c-old"}


def test_mark_review_lifecycle(db):
    _record(db, channel_id="c-1", now=dt.datetime(2026, 5, 10, 9, 0))
    _record(db, channel_id="c-1", now=dt.datetime(2026, 5, 10, 9, 5))
    store.mark_review_start(db, "c-1", "2026-05-10", now=dt.datetime(2026, 5, 11, 23, 0))
    row = store.get_session_row(db, "c-1", "2026-05-10")
    assert row["review_status"] == "running"
    store.mark_reviewed(db, "c-1", "2026-05-10", "done", "skills/x.md に追記",
                        now=dt.datetime(2026, 5, 11, 23, 2))
    row = store.get_session_row(db, "c-1", "2026-05-10")
    assert row["review_status"] == "done"
    assert row["reviewed_at"].startswith("2026-05-11T23:02")
    assert row["review_note"] == "skills/x.md に追記"
    # done になったら list_pending_reviews に出ない
    assert store.list_pending_reviews(db, today=dt.date(2026, 5, 12)) == []


def test_requeue_stuck(db):
    _record(db, channel_id="c-1", now=dt.datetime(2026, 5, 10, 9, 0))
    _record(db, channel_id="c-1", now=dt.datetime(2026, 5, 10, 9, 5))
    store.mark_review_start(db, "c-1", "2026-05-10", now=dt.datetime(2026, 5, 11, 22, 0))
    # 31分後にチェック → stuck とみなして running を解除
    store.requeue_stuck(db, stuck_minutes=30, now=dt.datetime(2026, 5, 11, 22, 31))
    row = store.get_session_row(db, "c-1", "2026-05-10")
    assert row["review_status"] is None
    assert row["review_started_at"] is None


def test_mark_short_skipped(db):
    _record(db, channel_id="c-short", now=dt.datetime(2026, 5, 10, 9, 0))
    store.mark_short_skipped(db, today=dt.date(2026, 5, 11), min_turns=2)
    row = store.get_session_row(db, "c-short", "2026-05-10")
    assert row["review_status"] == "skipped"
    assert row["review_note"] == "too_short"
```

- [ ] **Step 2: 実行して失敗を確認**

Run: `cd products/d-manager && python -m pytest tests/test_learning_store.py -q`
Expected: FAIL（`AttributeError: module 'learning.store' has no attribute 'list_pending_reviews'` 等）

- [ ] **Step 3: store.py に追記**

`products/d-manager/learning/store.py` の末尾に追加:
```python
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


def mark_review_start(db_path: Path, channel_id: str, review_date: str,
                      now: Optional[dt.datetime] = None) -> None:
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


def mark_reviewed(db_path: Path, channel_id: str, review_date: str, status: str,
                  note: str = "", now: Optional[dt.datetime] = None) -> None:
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


def requeue_stuck(db_path: Path, stuck_minutes: int = 30,
                  now: Optional[dt.datetime] = None) -> int:
    """review_status='running' のまま stuck_minutes 超のものを NULL に戻す。戻した件数を返す。"""
    now = now or dt.datetime.now()
    threshold = (now - dt.timedelta(minutes=stuck_minutes)).strftime("%Y-%m-%dT%H:%M:%S")
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


def mark_short_skipped(db_path: Path, today: Optional[dt.date] = None,
                       min_turns: int = 2) -> int:
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
```

- [ ] **Step 4: 実行して通ることを確認**

Run: `cd products/d-manager && python -m pytest tests/test_learning_store.py -q`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add products/d-manager/learning/store.py products/d-manager/tests/test_learning_store.py
git commit -m "feat(d-manager): learning store のレビュー台帳操作（pending/mark/requeue/skip）"
```

---

## Task 5: store.py — search（FTS5 trigram + LIKE フォールバック）と prune とメトリクス

**Files:**
- Modify: `products/d-manager/learning/store.py`
- Modify: `products/d-manager/tests/test_learning_store.py`

- [ ] **Step 1: 失敗するテストを追記**

`products/d-manager/tests/test_learning_store.py` の末尾に追加:
```python
def test_search_trigram_and_like_fallback(db):
    _record(db, content="元彼との復縁相談をした", now=dt.datetime(2026, 5, 10, 9, 0))
    _record(db, content="メルカリ仕入れの話", now=dt.datetime(2026, 5, 10, 9, 5))
    # 3文字以上 → FTS5 trigram
    hits3 = store.search(db, "復縁相談")
    assert any("復縁" in h["content"] for h in hits3)
    assert all("メルカリ" not in h["content"] for h in hits3)
    # 2文字 → LIKE フォールバック
    hits2 = store.search(db, "復縁")
    assert any("復縁" in h["content"] for h in hits2)


def test_prune_old_turns(db):
    _record(db, channel_id="c-old", content="古い", now=dt.datetime(2026, 1, 1, 9, 0))
    _record(db, channel_id="c-old", content="古い2", now=dt.datetime(2026, 1, 1, 9, 5))
    _record(db, channel_id="c-new", content="新しい", now=dt.datetime(2026, 5, 10, 9, 0))
    _record(db, channel_id="c-new", content="新しい2", now=dt.datetime(2026, 5, 10, 9, 5))
    deleted = store.prune(db, retention_days=30, now=dt.datetime(2026, 5, 12, 0, 0))
    assert deleted == 2
    # turns_fts も連動して消えている（古い語で検索しても出ない）
    assert store.search(db, "古い") == []
    # 新しい turns は残る
    assert len(store.get_session_turns(db, "c-new", "2026-05-10")) == 2
    # sessions 台帳は残す（集計用）
    assert store.get_session_row(db, "c-old", "2026-01-01") is not None


def test_skill_metrics(db, tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "a.md").write_text("x" * 1000, encoding="utf-8")
    (skills_dir / "b").mkdir()
    (skills_dir / "b" / "SKILL.md").write_text("y" * 500, encoding="utf-8")
    (skills_dir / "b" / "references").mkdir()
    (skills_dir / "b" / "references" / "long.md").write_text("z" * 9999, encoding="utf-8")
    m = store.skill_metrics(skills_dir)
    assert m["count"] == 2  # a.md と b/SKILL.md
    # references は数えない
    assert m["concat_chars"] == 1500
```

- [ ] **Step 2: 実行して失敗を確認**

Run: `cd products/d-manager && python -m pytest tests/test_learning_store.py -q`
Expected: FAIL（`AttributeError: ... 'search'`）

- [ ] **Step 3: store.py に追記**

`products/d-manager/learning/store.py` の末尾に追加:
```python
def search(db_path: Path, query: str, limit: int = 50) -> list[dict]:
    """会話ログ全文検索。3文字以上は FTS5 trigram、2文字以下は LIKE フォールバック。"""
    query = (query or "").strip()
    if not query:
        return []
    conn = _connect(db_path)
    try:
        if len(query) >= 3:
            rows = conn.execute(
                "SELECT t.channel_name, t.department, t.ts, t.role, t.content, t.review_date "
                "FROM turns_fts f JOIN turns t ON t.id = f.rowid "
                "WHERE turns_fts MATCH ? ORDER BY t.ts DESC LIMIT ?",
                (query, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT channel_name, department, ts, role, content, review_date "
                "FROM turns WHERE content LIKE ? ORDER BY ts DESC LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def prune(db_path: Path, retention_days: int = 180,
          now: Optional[dt.datetime] = None) -> int:
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
    for entry in sorted(skills_dir.iterdir()):
        if entry.name.startswith("."):
            continue  # .archive / .snapshots を除外
        if entry.is_file() and entry.suffix == ".md":
            count += 1
            concat_chars += len(entry.read_text(encoding="utf-8"))
        elif entry.is_dir():
            skill_md = entry / "SKILL.md"
            if skill_md.exists():
                count += 1
                concat_chars += len(skill_md.read_text(encoding="utf-8"))
    return {"count": count, "concat_chars": concat_chars}
```

- [ ] **Step 4: 実行して通ることを確認**

Run: `cd products/d-manager && python -m pytest tests/test_learning_store.py -q`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add products/d-manager/learning/store.py products/d-manager/tests/test_learning_store.py
git commit -m "feat(d-manager): learning store の search/prune/skill_metrics"
```

---

## Task 6: cli_runner.py — claude -p ラッパと git ヘルパ

**Files:**
- Create: `products/d-manager/learning/cli_runner.py`

（このモジュールは外部プロセスを叩くので、ユニットテストはモック側で行う。ここでは実装のみ。）

- [ ] **Step 1: cli_runner.py を実装**

`products/d-manager/learning/cli_runner.py`:
```python
"""`claude -p`（Claude Code CLI）をサブプロセス起動する薄いラッパと git ヘルパ。

reviewer.py / curator.py が共用する。d-manager 本体の ai_engine._process_cli と同じく
`cwd=COMPANY_DIR`・`--dangerously-skip-permissions` で動かすが、ツールは allowedTools/disallowedTools で絞る。
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CliResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool


def run_claude(
    prompt: str,
    cwd: Path,
    model: str,
    allowed_tools: str,
    disallowed_tools: str,
    system_prompt_append: str,
    max_turns: int,
    timeout_sec: int,
) -> CliResult:
    cmd = [
        "claude", "-p", prompt,
        "--model", model,
        "--allowedTools", allowed_tools,
        "--disallowedTools", disallowed_tools,
        "--append-system-prompt", system_prompt_append,
        "--max-turns", str(max_turns),
        "--dangerously-skip-permissions",
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout_sec
        )
        return CliResult(
            ok=(proc.returncode == 0),
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            returncode=proc.returncode,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as e:
        logger.warning("claude -p timed out after %ss", timeout_sec)
        return CliResult(ok=False, stdout=(e.stdout or "") if isinstance(e.stdout, str) else "",
                         stderr="timeout", returncode=-1, timed_out=True)
    except FileNotFoundError:
        logger.error("`claude` CLI not found on PATH")
        return CliResult(ok=False, stdout="", stderr="claude-cli-not-found",
                         returncode=-1, timed_out=False)


def git_head(repo: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def git_status_short(repo: Path) -> list[str]:
    """`git status --short` の各行（"XY path" 形式）をリストで返す。"""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "status", "--short"],
            capture_output=True, text=True
        ).stdout
        return [ln for ln in out.splitlines() if ln.strip()]
    except Exception:  # noqa: BLE001
        return []


def git_checkout_paths(repo: Path, paths: list[str]) -> None:
    if not paths:
        return
    try:
        subprocess.run(["git", "-C", str(repo), "checkout", "--"] + paths,
                       capture_output=True, text=True)
    except Exception:  # noqa: BLE001
        logger.exception("git checkout for out-of-bounds revert failed")


def parse_status_path(line: str) -> str:
    """`git status --short` の1行からパス部分を取り出す（"?? path" / " M path" / "A  path" 等）。"""
    # 先頭2文字 = ステータス、その後スペース1つ、残りがパス（リネームは ' -> ' を含む → 右側を取る）
    rest = line[3:] if len(line) > 3 else line.strip()
    if " -> " in rest:
        rest = rest.split(" -> ", 1)[1]
    return rest.strip().strip('"')


# 学習ループが書き込んでよい .company/ 配下のディレクトリ/ファイル（プレフィックス一致で判定）
ALLOWED_WRITE_PREFIXES = (
    "skills/",
    "secretary/memory/",
    "secretary/rules.md",
)


def out_of_bounds_paths(repo: Path, status_lines: list[str], extra_allowed: tuple = ()) -> list[str]:
    """git status の変更パスのうち、許可プレフィックスにも extra_allowed（例: `<dept>/knowledge/`）にも
    該当しないものを返す。`<dept>/knowledge/` は固定列挙が難しいので、呼び出し側が
    `("operations/knowledge/", "research/knowledge/", ...)` のように渡すか、後述の DEPT_KNOWLEDGE_PREFIXES を使う。
    """
    bad = []
    allowed = ALLOWED_WRITE_PREFIXES + tuple(extra_allowed)
    for ln in status_lines:
        p = parse_status_path(ln)
        if not any(p.startswith(a) for a in allowed):
            bad.append(p)
    return bad


# .company/<dept>/knowledge/ の dept 一覧（CLAUDE.md の組織図に対応）
DEPT_KNOWLEDGE_PREFIXES = tuple(
    f"{d}/knowledge/" for d in
    ("operations", "product", "marketing", "finance", "research", "strategy", "secretary")
)
```

- [ ] **Step 2: import が通ることを確認**

Run: `cd products/d-manager && python -c "from learning import cli_runner; print(cli_runner.ALLOWED_WRITE_PREFIXES, cli_runner.DEPT_KNOWLEDGE_PREFIXES)"`
Expected: タプルが2つ表示され、例外なし。

- [ ] **Step 3: Commit**

```bash
git add products/d-manager/learning/cli_runner.py
git commit -m "feat(d-manager): learning の claude -p ラッパと git ヘルパ"
```

---

## Task 7: reviewer.py — プロンプトと会話ログ整形（純粋関数部分）

**Files:**
- Create: `products/d-manager/learning/reviewer.py`
- Create: `products/d-manager/tests/test_learning_reviewer.py`

- [ ] **Step 1: 失敗するテストを書く**

`products/d-manager/tests/test_learning_reviewer.py`:
```python
from __future__ import annotations

import datetime as dt

from learning import reviewer


def test_format_conversation_log():
    turns = [
        {"turn_idx": 0, "role": "user", "content": "メルカリ仕入れの重複チェックは？",
         "ts": "2026-05-10T09:00:00", "department": "operations", "channel_name": "運営-jack-operations"},
        {"turn_idx": 1, "role": "assistant", "content": "出品済みSKUと照合してから…",
         "ts": "2026-05-10T09:00:05", "department": "operations", "channel_name": "運営-jack-operations"},
    ]
    log = reviewer.format_conversation_log("運営-jack-operations", "operations", "2026-05-10", turns)
    assert "運営-jack-operations" in log
    assert "operations" in log
    assert "2026-05-10" in log
    assert "[user]" in log and "[assistant]" in log
    assert "メルカリ仕入れ" in log
    assert "出品済みSKU" in log


def test_truncate_keeps_head_and_tail():
    turns = [
        {"turn_idx": i, "role": "user" if i % 2 == 0 else "assistant",
         "content": f"line-{i}-" + "x" * 200, "ts": f"2026-05-10T09:{i:02d}:00",
         "department": "operations", "channel_name": "c"}
        for i in range(60)
    ]
    log = reviewer.format_conversation_log("c", "operations", "2026-05-10", turns, char_limit=2000)
    assert len(log) <= 2500  # 上限 + マーカー分の余裕
    assert "line-0-" in log         # 先頭は残る
    assert "line-59-" in log        # 末尾は残る
    assert "（中略" in log


def test_parse_summary():
    out = "作業しました。\n色々やった。\n<summary>done: skills/x.md に追記</summary>\n"
    s = reviewer.parse_summary(out)
    assert s == ("done", "skills/x.md に追記")

    out2 = "<summary>no_learnings: 在庫確認のみ</summary>"
    assert reviewer.parse_summary(out2) == ("no_learnings", "在庫確認のみ")

    # summary 無し → None
    assert reviewer.parse_summary("何も返ってこなかった") is None
```

- [ ] **Step 2: 実行して失敗を確認**

Run: `cd products/d-manager && python -m pytest tests/test_learning_reviewer.py -q`
Expected: FAIL（`ModuleNotFoundError` / `AttributeError`）

- [ ] **Step 3: reviewer.py を実装（純粋関数部分 + プロンプト定数）**

`products/d-manager/learning/reviewer.py`:
```python
"""学習レビュアー — 1セッション（チャンネル+日付）の会話を振り返り、.company/ の skill/memory/rules を更新する。

# Adapted from Hermes Agent (MIT) — github.com/NousResearch/hermes-agent
# REVIEWER_PERSONA / REVIEW_PROMPT は Hermes の _COMBINED_REVIEW_PROMPT と "do NOT capture" ブロックリストをベースに移植。
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SUMMARY_RE = re.compile(r"<summary>\s*(\w+)\s*:\s*(.*?)\s*</summary>", re.DOTALL)


def parse_summary(text: str) -> Optional[tuple[str, str]]:
    """出力末尾の <summary>status: note</summary> を (status, note) で返す。無ければ None。"""
    matches = list(_SUMMARY_RE.finditer(text or ""))
    if not matches:
        return None
    m = matches[-1]
    return (m.group(1).strip(), m.group(2).strip())


def format_conversation_log(
    channel_name: str,
    department: str,
    review_date: str,
    turns: list[dict],
    char_limit: int = 40000,
) -> str:
    header = f"## 会話ログ — {channel_name} / {department} / {review_date}\n"
    lines = [f"[{t['role']}] {t['content']}" for t in turns]
    body = "\n".join(lines)
    full = header + body
    if len(full) <= char_limit:
        return full
    # 先頭20% + 末尾60%（末尾＝結論・つまずき解決が出やすい）、中略マーカー
    head_n = int(char_limit * 0.2)
    tail_n = int(char_limit * 0.6)
    head = body[:head_n]
    tail = body[-tail_n:]
    omitted = len(body) - head_n - tail_n
    return f"{header}{head}\n\n（中略 — 約{omitted}文字省略）\n\n{tail}"


REVIEWER_PERSONA = """あなたは TrustLink の学習レビュアーです。12名のAI社員のような人格は持ちません。
1つの会話ログを読み、次回以降の再現性につながる学びだけを `.company/` の所定の場所に書き込む単機能エージェントです。
社訓のうち次の3つを厳守: (1)嘘をつくな・捏造するな (2)古い情報を使い回すな・常に最新を取りに行け (7)学びを記録せよ。
あなたが使える操作はファイルの Read/Write/Edit/Glob/Grep のみです。
メール送信・eBay API・広告API・git push・外部コマンド実行など、ファイル更新以外のことは一切してはいけません。"""


def build_review_prompt(
    conversation_log: str,
    channel_name: str,
    department: str,
    review_date: str,
    recent_learnings: str,
    dryrun: bool,
    extra_context: str = "",
) -> str:
    """レビュー本体プロンプトを組み立てる。`recent_learnings` は直近7日に記録済みの学び一覧（重複防止）。"""
    dryrun_note = (
        "\n\n【ドライランモード】ファイルは一切書くな（Write/Edit するな）。"
        "もし本番なら何をどこに書くつもりだったかを <summary> に詳細に列挙せよ。"
        if dryrun else ""
    )
    return f"""以下は {channel_name}（部門: {department}）で {review_date} に交わされた会話ログです。
ここから「次回以降の再現性につながる学び」だけを抽出し、`.company/` の適切な場所を更新してください。
学びが無ければ何もせず、最後に `<summary>no_learnings: 理由</summary>` だけ返してください。{dryrun_note}

## 書き込み先の振り分け
- 再現性のある手順（「Xをやるときはこの順で」）→ `.company/skills/<name>.md`（既存スキルに追記できるなら新規作成せず Edit を優先。スキル本文が概ね80-100行を超えそうなら、骨子だけ `<name>/SKILL.md` に残し、詳細・長いサンプル・チェックリストは `<name>/references/*.md` に分けて作る）。frontmatter は `name` / `owner` / `trigger`。
- 確定した事実（「クライアントAの請求書は月末締め」など）→ `.company/secretary/memory/facts/<topic>.md`（1行ずつ。同じ趣旨が既にあれば追記しない。宣言形で書く＝「〜である」、「〜せよ」ではない）。
- 振り返り知見（「この施策はこういう理由で効いた」）→ `.company/secretary/memory/digest/<topic>.md`（`## {review_date}` の見出しの下に書く）。
- 「2回以上同じ指摘を受けた」級の運用ルール → `.company/secretary/rules.md`（既存の追記フォーマットに合わせる）。
- 部門固有の業務知識 → `.company/{department}/knowledge/<topic>.md`（500行を超えそうなら分割）。

## 保存してはいけないもの（重要）
- 環境依存の失敗（APIキー切れ・ネット断・特定マシン固有の事象）。これを「〜は使えない」という恒久ルールに固めるな。
- ツールへの否定的主張（「Xは動かない」を恒久ルール化しない）。
- 一過性のエラー・リトライで直ったもの。
- 一回限りのタスクの語り（「今日Aさんに返信した」自体は記録不要。そこから学んだ"やり方"だけ）。
- 既に `.company/skills/` や `.company/secretary/rules.md` に書いてあること（重複）。事前に Grep で確認すること。
- 新しい狭いスキルを作るより、既存の包括スキルにパッチを当てる方を常に優先せよ。

## 既に記録済みの学び（重複チェック用・抜粋）
{recent_learnings or "(なし)"}

{extra_context}

## 会話ログ
{conversation_log}

---
作業が終わったら、必ず最後に1つだけ `<summary>` ブロックを返してください。
- 何か書いた場合: `<summary>done: 何をどこに書いたか（ファイルパスと一言）</summary>`
- 学びが無かった場合: `<summary>no_learnings: 理由</summary>`
"""
```

- [ ] **Step 4: 実行して通ることを確認**

Run: `cd products/d-manager && python -m pytest tests/test_learning_reviewer.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add products/d-manager/learning/reviewer.py products/d-manager/tests/test_learning_reviewer.py
git commit -m "feat(d-manager): learning reviewer のプロンプト・会話ログ整形・summary パース"
```

---

## Task 8: reviewer.py — run_review（subprocess 起動 + 範囲外 revert + skill_hits 記録）

**Files:**
- Modify: `products/d-manager/learning/reviewer.py`
- Modify: `products/d-manager/tests/test_learning_reviewer.py`

- [ ] **Step 1: 失敗するテストを追記**

`products/d-manager/tests/test_learning_reviewer.py` の末尾に追加:
```python
import datetime as dt
from pathlib import Path

import pytest

from learning import store, cli_runner


@pytest.fixture
def setup(tmp_path, monkeypatch):
    db = tmp_path / "c.db"
    store.init_db(db)
    company = tmp_path / "company"
    (company / "skills").mkdir(parents=True)
    (company / "secretary" / "memory" / "facts").mkdir(parents=True)
    # ダミー会話
    for i in range(4):
        store.record_turn(db, "chan-1", "運営-jack-operations", "operations", "s-1",
                          "user" if i % 2 == 0 else "assistant", f"msg-{i}",
                          "cli", "chat", True, now=dt.datetime(2026, 5, 10, 9, i, 0))
    return db, company


def _fake_cli(stdout: str, ok=True, timed_out=False, returncode=0):
    def _run(**kwargs):
        return cli_runner.CliResult(ok=ok, stdout=stdout, stderr="" if ok else "boom",
                                    returncode=returncode, timed_out=timed_out)
    return _run


def test_run_review_done(setup, monkeypatch):
    db, company = setup
    monkeypatch.setattr(cli_runner, "run_claude",
                        _fake_cli("やった\n<summary>done: skills/x.md に追記</summary>"))
    monkeypatch.setattr(cli_runner, "git_status_short", lambda repo: ["A  skills/x.md"])
    monkeypatch.setattr(cli_runner, "git_head", lambda repo: "deadbeef")
    reverted = []
    monkeypatch.setattr(cli_runner, "git_checkout_paths", lambda repo, paths: reverted.extend(paths))

    res = reviewer.run_review(db_path=db, company_dir=company, channel_id="chan-1",
                              review_date="2026-05-10", channel_name="運営-jack-operations",
                              department="operations", model="m", dryrun=False,
                              now=dt.datetime(2026, 5, 11, 23, 0))
    assert res["status"] == "done"
    assert "skills/x.md" in res["note"]
    assert reverted == []  # 範囲内なので revert されない
    row = store.get_session_row(db, "chan-1", "2026-05-10")
    assert row["review_status"] == "done"


def test_run_review_no_learnings(setup, monkeypatch):
    db, company = setup
    monkeypatch.setattr(cli_runner, "run_claude", _fake_cli("<summary>no_learnings: 雑談</summary>"))
    monkeypatch.setattr(cli_runner, "git_status_short", lambda repo: [])
    monkeypatch.setattr(cli_runner, "git_head", lambda repo: "x")
    monkeypatch.setattr(cli_runner, "git_checkout_paths", lambda repo, paths: None)
    res = reviewer.run_review(db_path=db, company_dir=company, channel_id="chan-1",
                              review_date="2026-05-10", channel_name="c", department="operations",
                              model="m", dryrun=False, now=dt.datetime(2026, 5, 11, 23, 0))
    assert res["status"] == "done"
    assert res["note"].startswith("no_learnings")


def test_run_review_timeout(setup, monkeypatch):
    db, company = setup
    monkeypatch.setattr(cli_runner, "run_claude", _fake_cli("", ok=False, timed_out=True, returncode=-1))
    monkeypatch.setattr(cli_runner, "git_status_short", lambda repo: [])
    monkeypatch.setattr(cli_runner, "git_head", lambda repo: "x")
    monkeypatch.setattr(cli_runner, "git_checkout_paths", lambda repo, paths: None)
    res = reviewer.run_review(db_path=db, company_dir=company, channel_id="chan-1",
                              review_date="2026-05-10", channel_name="c", department="operations",
                              model="m", dryrun=False, now=dt.datetime(2026, 5, 11, 23, 0))
    assert res["status"] == "error"
    assert "timeout" in res["note"]
    row = store.get_session_row(db, "chan-1", "2026-05-10")
    assert row["review_status"] == "error"


def test_run_review_no_summary(setup, monkeypatch):
    db, company = setup
    monkeypatch.setattr(cli_runner, "run_claude", _fake_cli("何か作業はしたが summary を返し忘れた"))
    monkeypatch.setattr(cli_runner, "git_status_short", lambda repo: [])
    monkeypatch.setattr(cli_runner, "git_head", lambda repo: "x")
    monkeypatch.setattr(cli_runner, "git_checkout_paths", lambda repo, paths: None)
    res = reviewer.run_review(db_path=db, company_dir=company, channel_id="chan-1",
                              review_date="2026-05-10", channel_name="c", department="operations",
                              model="m", dryrun=False, now=dt.datetime(2026, 5, 11, 23, 0))
    assert res["status"] == "error"
    assert "no_summary" in res["note"]


def test_run_review_out_of_bounds_reverted(setup, monkeypatch):
    db, company = setup
    monkeypatch.setattr(cli_runner, "run_claude",
                        _fake_cli("<summary>done: なんか色々</summary>"))
    # .env を触ってしまったケース
    monkeypatch.setattr(cli_runner, "git_status_short", lambda repo: [" M .env", "A  skills/x.md"])
    monkeypatch.setattr(cli_runner, "git_head", lambda repo: "x")
    reverted = []
    monkeypatch.setattr(cli_runner, "git_checkout_paths", lambda repo, paths: reverted.extend(paths))
    res = reviewer.run_review(db_path=db, company_dir=company, channel_id="chan-1",
                              review_date="2026-05-10", channel_name="c", department="operations",
                              model="m", dryrun=False, now=dt.datetime(2026, 5, 11, 23, 0))
    assert ".env" in reverted
    assert "skills/x.md" not in reverted
    assert res["out_of_bounds"] == [".env"]


def test_run_review_dryrun_restricts_tools(setup, monkeypatch):
    db, company = setup
    captured = {}
    def _capture(**kwargs):
        captured.update(kwargs)
        return cli_runner.CliResult(True, "<summary>no_learnings: dryrun</summary>", "", 0, False)
    monkeypatch.setattr(cli_runner, "run_claude", _capture)
    monkeypatch.setattr(cli_runner, "git_status_short", lambda repo: [])
    monkeypatch.setattr(cli_runner, "git_head", lambda repo: "x")
    monkeypatch.setattr(cli_runner, "git_checkout_paths", lambda repo, paths: None)
    reviewer.run_review(db_path=db, company_dir=company, channel_id="chan-1",
                        review_date="2026-05-10", channel_name="c", department="operations",
                        model="m", dryrun=True, now=dt.datetime(2026, 5, 11, 23, 0))
    assert "Write" not in captured["allowed_tools"]
    assert "Edit" not in captured["allowed_tools"]
    assert "Bash" in captured["disallowed_tools"]
```

- [ ] **Step 2: 実行して失敗を確認**

Run: `cd products/d-manager && python -m pytest tests/test_learning_reviewer.py -q`
Expected: FAIL（`AttributeError: ... 'run_review'`）

- [ ] **Step 3: reviewer.py に run_review を追記**

`products/d-manager/learning/reviewer.py` の末尾に追加（import を先頭に追加: `import json` `import config` は不要 — reviewer は config を直接読まず、必要な値は引数で受ける方針。ただし `from . import cli_runner, store` を先頭の import 群に追加）:

ファイル先頭の import 群を次のように調整:
```python
from __future__ import annotations

import datetime as dt
import json
import logging
import re
from pathlib import Path
from typing import Optional

from . import cli_runner, store
```

末尾に追加:
```python
def _read_recent_learnings(company_dir: Path, days: int = 7, max_chars: int = 4000) -> str:
    """直近 `days` 日に記録された学びを抜粋（重複チェック用）。Company/Logs と memory/{facts,digest} から。"""
    chunks: list[str] = []
    logs_dir = company_dir.parent / "Company" / "Logs"  # .company の隣の Company/Logs（環境により異なる場合は存在チェックで吸収）
    today = dt.date.today()
    for i in range(days):
        d = (today - dt.timedelta(days=i)).strftime("%Y-%m-%d")
        for cand in (logs_dir / f"{d}.md", company_dir / "secretary" / "memory" / "raw" / f"{d}.md"):
            if cand.exists():
                chunks.append(f"### {cand}\n" + cand.read_text(encoding="utf-8")[:1500])
    # facts / digest は最近更新されたものを数件
    for sub in ("facts", "digest"):
        d = company_dir / "secretary" / "memory" / sub
        if d.exists():
            files = sorted(d.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
            for f in files:
                chunks.append(f"### memory/{sub}/{f.name}\n" + f.read_text(encoding="utf-8")[:800])
    text = "\n\n".join(chunks)
    return text[:max_chars]


def _record_skill_hits(skill_hits_path: Path, channel_name: str, review_date: str,
                       company_dir: Path, status_lines: list[str]) -> None:
    """このレビューで触れた skills/ ファイルを skill_hits.jsonl に追記（キュレーターの利用判定材料）。"""
    try:
        skill_hits_path.parent.mkdir(parents=True, exist_ok=True)
        with skill_hits_path.open("a", encoding="utf-8") as fh:
            for ln in status_lines:
                p = cli_runner.parse_status_path(ln)
                if p.startswith("skills/"):
                    name = p[len("skills/"):].split("/")[0].removesuffix(".md")
                    fh.write(json.dumps({"skill": name, "channel": channel_name,
                                         "date": review_date}, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        logger.exception("skill_hits 記録に失敗")


def run_review(
    db_path: Path,
    company_dir: Path,
    channel_id: str,
    review_date: str,
    channel_name: str,
    department: str,
    model: str,
    dryrun: bool,
    *,
    allowed_tools: str = "Read Write Edit Glob Grep",
    dryrun_allowed_tools: str = "Read Glob Grep",
    disallowed_tools: str = "Bash WebFetch WebSearch Task",
    char_limit: int = 40000,
    max_turns: int = 15,
    timeout_sec: int = 300,
    skill_hits_path: Optional[Path] = None,
    extra_context: str = "",
    now: Optional[dt.datetime] = None,
) -> dict:
    """1セッションを振り返る。戻り値: {status, note, out_of_bounds, head_before}。"""
    store.mark_review_start(db_path, channel_id, review_date, now=now)
    turns = store.get_session_turns(db_path, channel_id, review_date)
    conv_log = format_conversation_log(channel_name, department, review_date, turns, char_limit=char_limit)
    recent = _read_recent_learnings(company_dir)
    prompt = build_review_prompt(conv_log, channel_name, department, review_date, recent, dryrun, extra_context)
    used_allowed = dryrun_allowed_tools if dryrun else allowed_tools

    head_before = cli_runner.git_head(company_dir)
    result = cli_runner.run_claude(
        prompt=prompt, cwd=company_dir, model=model,
        allowed_tools=used_allowed, disallowed_tools=disallowed_tools,
        system_prompt_append=REVIEWER_PERSONA, max_turns=max_turns, timeout_sec=timeout_sec,
    )

    status_lines = cli_runner.git_status_short(company_dir)
    extra_allowed = cli_runner.DEPT_KNOWLEDGE_PREFIXES
    oob = cli_runner.out_of_bounds_paths(company_dir, status_lines, extra_allowed=extra_allowed)
    if oob and not dryrun:
        cli_runner.git_checkout_paths(company_dir, oob)
        logger.warning("learning reviewer touched out-of-bounds paths, reverted: %s", oob)

    if result.timed_out:
        status, note = "error", "timeout"
    elif not result.ok:
        status, note = "error", f"exit={result.returncode}: {result.stderr[-300:]}"
    else:
        parsed = parse_summary(result.stdout)
        if parsed is None:
            status, note = "error", "no_summary"
        elif parsed[0] == "no_learnings":
            status, note = "done", f"no_learnings: {parsed[1]}"
        else:
            status, note = "done", parsed[1] or parsed[0]

    if status == "done" and not dryrun and skill_hits_path is not None:
        _record_skill_hits(skill_hits_path, channel_name, review_date, company_dir, status_lines)

    store.mark_reviewed(db_path, channel_id, review_date, status, note, now=now)
    return {"status": status, "note": note, "out_of_bounds": oob, "head_before": head_before}
```

注: `_read_recent_learnings` の `Company/Logs` パスは環境依存（`COMPANY_DIR` の隣に `Company/` がある構成）。存在チェックで吸収しているので、無ければ単にスキップされる。

- [ ] **Step 4: 実行して通ることを確認**

Run: `cd products/d-manager && python -m pytest tests/test_learning_reviewer.py -q`
Expected: 9 passed（前タスクの3 + 今回の6）

- [ ] **Step 5: Commit**

```bash
git add products/d-manager/learning/reviewer.py products/d-manager/tests/test_learning_reviewer.py
git commit -m "feat(d-manager): learning reviewer の run_review（subprocess+範囲外revert+skill_hits）"
```

---

## Task 9: ai_engine.py — record_turn フックを差し込む

**Files:**
- Modify: `products/d-manager/ai_engine.py`

（このフックは外部I/O＝ライブの discord/claude に依存するためユニットテストは置かず、import スモークと手動確認で担保する。）

- [ ] **Step 1: ai_engine.py の先頭に学習ログ用ヘルパを追加**

`ai_engine.py` の import 群（`import config` のあたり）の下に、次のヘルパとカウンタを追加する:
```python
# ── 学習ループ: 会話ログ記録 ──────────────────────────────────────────────
try:
    from learning import store as _learning_store
except Exception:  # noqa: BLE001  学習モジュールが無くても本処理は動く
    _learning_store = None

_learning_record_fail_count = 0


def _learning_origin(channel_id: str) -> tuple[str, bool]:
    """channel_id から (origin, reviewable) を決める。
    scheduler-* / agent-call-* は人手の会話ではないので reviewable=False（spec §1）。"""
    cid = channel_id if isinstance(channel_id, str) else str(channel_id)
    if cid.startswith("scheduler-"):
        return f"scheduler:{cid}", False
    if cid.startswith("agent-call-"):
        return "agent-call", False
    return "chat", True


def _record_learning_turn(channel_id: str, department: str, engine: str,
                          cli_session_id, user_message: str, assistant_reply: str) -> None:
    """user/assistant の2ターンを learning store に記録。失敗しても本処理は止めない。"""
    global _learning_record_fail_count
    if _learning_store is None:
        return
    try:
        channel_name = None
        # CHANNEL_MAP の逆引き（id→name）は持っていないので、channel_id の prefix で origin を決める
        origin, reviewable = _learning_origin(str(channel_id))
        for role, content in (("user", user_message), ("assistant", assistant_reply)):
            _learning_store.record_turn(
                db_path=config.LEARNING_DB_PATH, channel_id=str(channel_id),
                channel_name=channel_name, department=department,
                cli_session_id=cli_session_id, role=role, content=content,
                engine=engine, origin=origin, reviewable=reviewable,
            )
        _learning_record_fail_count = 0
    except Exception:  # noqa: BLE001
        _learning_record_fail_count += 1
        logger.exception("learning turn 記録に失敗（連続 %d 回目）", _learning_record_fail_count)
        if _learning_record_fail_count >= 10:
            try:
                from main import notify_learning_alert  # 遅延 import で循環回避
                notify_learning_alert("⚠️ 学習ログDB（conversations.db）が連続10回書けていません。確認してください。")
            except Exception:  # noqa: BLE001
                pass
            _learning_record_fail_count = 0
```

注: `notify_learning_alert` は Task 13 で `main.py` に作る。まだ無い段階では `except` で握りつぶされるだけなので、このタスク単独で import エラーにはならない。

- [ ] **Step 2: `_process_cli` の正常 return の直前に記録を挟む**

`ai_engine.py` の `_process_cli` を開き、正常系の `return result.stdout.strip()`（spec の前提で末尾付近にある。複数 return がある場合はサブプロセスが正常終了した分岐）を探す。`reply = result.stdout.strip()` という中間変数に置き換え、その直後・`return` の前に記録を入れる:

変更前（イメージ）:
```python
            return result.stdout.strip()
```
変更後:
```python
            reply = result.stdout.strip()
            _record_learning_turn(channel_id, department, "cli", session_id, user_message, reply)
            return reply
```

`session_id` はその関数内で `_get_or_create_cli_session(channel_id)` から得ているはず（spec の前提）。変数名が違えば実際の名前に合わせる。`--resume` 失敗で新セッションを作り直して再実行する分岐にも同じ正常 return があれば、そこにも同じ2行を入れる（その場合の session_id はリトライ後の新 id）。タイムアウト・例外で `_process_api` に落ちる分岐や、空応答を返す分岐には**入れない**（失敗時は記録しない）。

- [ ] **Step 3: `_process_api` の正常 return の直前にも記録を挟む**

`_process_api` の正常系 return（`return result` 等）を探し、同様に:
```python
            _record_learning_turn(channel_id, department, "api", None, user_message, result)
            return result
```
複数の正常 return（リトライ後など）があれば、最終的に「ユーザーに返す応答が確定した1箇所」だけに入れる（二重記録を避ける）。エラーで空文字を返す分岐には入れない。

- [ ] **Step 4: import スモークと簡易動作確認**

Run: `cd products/d-manager && python -c "import ai_engine; print('import ok')"`
Expected: `import ok`（循環 import エラーが出ないこと）

Run（DB が作られ record_turn が動くことの簡易確認）:
```bash
cd products/d-manager && python -c "
import config, ai_engine
ai_engine._record_learning_turn('chan-test', 'operations', 'cli', 'sess-x', 'テスト質問', 'テスト回答')
from learning import store
print(store.get_session_turns(config.LEARNING_DB_PATH, 'chan-test', __import__('datetime').date.today().strftime('%Y-%m-%d')))
"
```
Expected: 2件のターン（user/assistant）が表示される。確認後、`products/d-manager/learning/conversations.db*` は gitignore 済みなのでそのままでよい（消したければ消す）。

- [ ] **Step 5: Commit**

```bash
git add products/d-manager/ai_engine.py
git commit -m "feat(d-manager): ai_engine に会話ログ記録フック（CLI/API 両モード）"
```

---

## Task 10: departments.py — references/ デュアルローダー + skills_concat_size

**Files:**
- Modify: `products/d-manager/departments.py`
- Create: `products/d-manager/tests/test_departments_loader.py`

- [ ] **Step 1: 失敗するテストを書く**

`products/d-manager/tests/test_departments_loader.py`:
```python
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def fake_company(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "COMPANY_DIR", tmp_path)
    (tmp_path / "CLAUDE.md").write_text("# company rules", encoding="utf-8")
    skills = tmp_path / "skills"
    skills.mkdir()
    # フラット形式
    (skills / "flat.md").write_text("FLAT-SKILL-BODY", encoding="utf-8")
    # 新形式（SKILL.md + references/）
    d = skills / "fancy"
    d.mkdir()
    (d / "SKILL.md").write_text("FANCY-SKILL-BODY 詳細は references/long.md を参照", encoding="utf-8")
    refs = d / "references"
    refs.mkdir()
    (refs / "long.md").write_text("REFERENCE-DETAIL-SHOULD-NOT-BE-CONCATENATED", encoding="utf-8")
    # .archive は無視されるべき
    arch = skills / ".archive"
    arch.mkdir()
    (arch / "old.md").write_text("ARCHIVED-SHOULD-NOT-APPEAR", encoding="utf-8")
    return tmp_path


def test_loader_includes_flat_and_skillmd_body_not_references(fake_company):
    import importlib
    import departments
    importlib.reload(departments)
    prompt = departments.load_department_prompt("operations")
    assert "FLAT-SKILL-BODY" in prompt
    assert "FANCY-SKILL-BODY" in prompt
    assert "REFERENCE-DETAIL-SHOULD-NOT-BE-CONCATENATED" not in prompt
    assert "ARCHIVED-SHOULD-NOT-APPEAR" not in prompt


def test_skills_concat_size(fake_company):
    import importlib
    import departments
    importlib.reload(departments)
    m = departments.skills_concat_size()
    assert m["count"] == 2
    # FLAT-SKILL-BODY (15) + FANCY-SKILL-BODY ... の文字数（references は含めない）
    assert m["concat_chars"] == len("FLAT-SKILL-BODY") + len("FANCY-SKILL-BODY 詳細は references/long.md を参照")


def test_skillmd_takes_priority_over_flat(fake_company):
    # skills/dup.md と skills/dup/SKILL.md が両方ある → SKILL.md 側を使う
    skills = fake_company / "skills"
    (skills / "dup.md").write_text("DUP-FLAT", encoding="utf-8")
    d = skills / "dup"
    d.mkdir()
    (d / "SKILL.md").write_text("DUP-NEW", encoding="utf-8")
    import importlib
    import departments
    importlib.reload(departments)
    prompt = departments.load_department_prompt("operations")
    assert "DUP-NEW" in prompt
    assert "DUP-FLAT" not in prompt
```

- [ ] **Step 2: 実行して失敗を確認**

Run: `cd products/d-manager && python -m pytest tests/test_departments_loader.py -q`
Expected: FAIL（現状の `glob("*.md")` だと `fancy/SKILL.md` を拾わず `.archive/old.md` も glob 対象外だが…実際は `fancy` ディレクトリ自体が `*.md` にマッチしないので FANCY-SKILL-BODY が出ず FAIL、`skills_concat_size` も未定義で FAIL）

- [ ] **Step 3: departments.py を書き換える**

`products/d-manager/departments.py` を次の内容に置き換える（既存の `load_department_prompt` の skills 読み込み部分を差し替え、`skills_concat_size` を追加）:
```python
"""Department AI personality loader."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import config


def _iter_skill_bodies(skills_dir: Path):
    """`.company/skills/` 配下のスキル本文を順に yield する。

    - `<name>.md`（フラット形式）→ 全文。
    - `<name>/SKILL.md`（新形式）→ SKILL.md の本文のみ（同ディレクトリの references/ は連結しない）。
    - 同名で両方ある場合は `<name>/SKILL.md` を優先。
    - 先頭が `.` のエントリ（`.archive` / `.snapshots` 等）は無視。
    """
    if not skills_dir.exists():
        return
    # まず新形式のディレクトリ名を集める（フラット側を抑止するため）
    dir_skills = {}
    for entry in sorted(skills_dir.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            skill_md = entry / "SKILL.md"
            if skill_md.exists():
                dir_skills[entry.name] = skill_md
    for name, skill_md in dir_skills.items():
        yield skill_md.read_text(encoding="utf-8")
    for entry in sorted(skills_dir.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_file() and entry.suffix == ".md":
            if entry.stem in dir_skills:
                continue  # 新形式が優先
            yield entry.read_text(encoding="utf-8")


def skills_concat_size() -> dict:
    """system prompt に連結される skills 部分の規模（メトリクス用）。"""
    skills_dir = config.COMPANY_DIR / "skills"
    count = 0
    chars = 0
    for body in _iter_skill_bodies(skills_dir):
        count += 1
        chars += len(body)
    return {"count": count, "concat_chars": chars}


def load_department_prompt(department: str) -> str:
    """Load CLAUDE.md for a department as system prompt."""
    company_rules = ""
    company_claude = config.COMPANY_DIR / "CLAUDE.md"
    if company_claude.exists():
        company_rules = company_claude.read_text(encoding="utf-8")

    dept_claude = config.COMPANY_DIR / department / "CLAUDE.md"
    dept_prompt = ""
    if dept_claude.exists():
        dept_prompt = dept_claude.read_text(encoding="utf-8")

    agents_dir = config.COMPANY_DIR / department / "agents"
    agent_prompts = ""
    if agents_dir.exists():
        for agent_file in sorted(agents_dir.glob("*.md")):
            agent_prompts += f"\n\n{agent_file.read_text(encoding='utf-8')}"

    skills_dir = config.COMPANY_DIR / "skills"
    skills_text = ""
    for body in _iter_skill_bodies(skills_dir):
        skills_text += f"\n\n{body}"

    return f"""{company_rules}

---

{dept_prompt}

{agent_prompts}

---

## 共通スキル
{skills_text}
"""


def get_department_for_channel(channel_name: str) -> str:
    """Map Discord channel name to department."""
    return config.CHANNEL_MAP.get(channel_name, "secretary")
```

- [ ] **Step 4: 実行して通ることを確認**

Run: `cd products/d-manager && python -m pytest tests/test_departments_loader.py -q`
Expected: 3 passed

また既存 import が壊れていないことを確認: `cd products/d-manager && python -c "import departments; print(departments.skills_concat_size())"`
Expected: 実際の `.company/skills/` の件数と文字数（例: `{'count': 6, 'concat_chars': ...}`）

- [ ] **Step 5: Commit**

```bash
git add products/d-manager/departments.py products/d-manager/tests/test_departments_loader.py
git commit -m "feat(d-manager): departments ローダーを references/ デュアル対応・連結サイズ計測を追加"
```

---

## Task 11: curator.py — CURATOR_PROMPT と run_curation

**Files:**
- Create: `products/d-manager/learning/curator.py`
- Create: `products/d-manager/tests/test_learning_curator.py`

- [ ] **Step 1: 失敗するテストを書く**

`products/d-manager/tests/test_learning_curator.py`:
```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from learning import curator, cli_runner


@pytest.fixture
def company(tmp_path):
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "a.md").write_text("# skill a\n owner: jack\n", encoding="utf-8")
    (skills / "b.md").write_text("# skill b\n owner: tim\n", encoding="utf-8")
    return tmp_path


def test_run_curation_parses_summary_and_snapshots(company, tmp_path, monkeypatch):
    snap_calls = []
    monkeypatch.setattr(curator, "_make_snapshot", lambda company_dir, keep: snap_calls.append("snap"))
    monkeypatch.setattr(cli_runner, "git_head", lambda repo: "abc123")
    monkeypatch.setattr(cli_runner, "git_status_short", lambda repo: ["A  skills/merged.md", " D skills/a.md"])
    monkeypatch.setattr(cli_runner, "git_checkout_paths", lambda repo, paths: None)
    monkeypatch.setattr(cli_runner, "run_claude",
                        lambda **kw: cli_runner.CliResult(
                            True, "棚卸ししました\n<summary>before=2 after=1 merged=[a->b] archived=[] created=[merged] fixed=[]</summary>",
                            "", 0, False))
    res = curator.run_curation(company_dir=company, model="m",
                               skill_hits_path=tmp_path / "skill_hits.jsonl", snapshot_keep=8)
    assert res["status"] == "done"
    assert "before=2 after=1" in res["summary"]
    assert res["head_before"] == "abc123"
    assert snap_calls == ["snap"]


def test_run_curation_reverts_out_of_bounds(company, tmp_path, monkeypatch):
    monkeypatch.setattr(curator, "_make_snapshot", lambda company_dir, keep: None)
    monkeypatch.setattr(cli_runner, "git_head", lambda repo: "x")
    # skills/.archive は許可、それ以外（secretary/decisions など）は範囲外
    monkeypatch.setattr(cli_runner, "git_status_short",
                        lambda repo: ["A  skills/.archive/old.md", " M secretary/decisions/foo.md"])
    reverted = []
    monkeypatch.setattr(cli_runner, "git_checkout_paths", lambda repo, paths: reverted.extend(paths))
    monkeypatch.setattr(cli_runner, "run_claude",
                        lambda **kw: cli_runner.CliResult(True, "<summary>before=2 after=2 merged=[] archived=[] created=[] fixed=[]</summary>", "", 0, False))
    curator.run_curation(company_dir=company, model="m", skill_hits_path=tmp_path / "h.jsonl", snapshot_keep=8)
    assert "secretary/decisions/foo.md" in reverted
    assert "skills/.archive/old.md" not in reverted


def test_run_curation_timeout(company, tmp_path, monkeypatch):
    monkeypatch.setattr(curator, "_make_snapshot", lambda company_dir, keep: None)
    monkeypatch.setattr(cli_runner, "git_head", lambda repo: "x")
    monkeypatch.setattr(cli_runner, "git_status_short", lambda repo: [])
    monkeypatch.setattr(cli_runner, "git_checkout_paths", lambda repo, paths: None)
    monkeypatch.setattr(cli_runner, "run_claude",
                        lambda **kw: cli_runner.CliResult(False, "", "timeout", -1, True))
    res = curator.run_curation(company_dir=company, model="m", skill_hits_path=tmp_path / "h.jsonl", snapshot_keep=8)
    assert res["status"] == "error"
    assert "timeout" in res["note"]
```

- [ ] **Step 2: 実行して失敗を確認**

Run: `cd products/d-manager && python -m pytest tests/test_learning_curator.py -q`
Expected: FAIL（`ModuleNotFoundError: learning.curator`）

- [ ] **Step 3: curator.py を実装**

`products/d-manager/learning/curator.py`:
```python
"""週次スキルキュレーター — `.company/skills/` を棚卸し（統合・アーカイブ・frontmatter 修正）。

# Adapted from Hermes Agent (MIT) — github.com/NousResearch/hermes-agent
# CURATOR_PERSONA / CURATOR_PROMPT は Hermes の CURATOR_REVIEW_PROMPT をベースに移植。
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import subprocess
import tarfile
from pathlib import Path
from typing import Optional

from . import cli_runner

logger = logging.getLogger(__name__)

_SUMMARY_RE = re.compile(r"<summary>(.*?)</summary>", re.DOTALL)


def _parse_summary(text: str) -> Optional[str]:
    m = list(_SUMMARY_RE.finditer(text or ""))
    return m[-1].group(1).strip() if m else None


def _make_snapshot(company_dir: Path, keep: int = 8) -> None:
    """`.company/skills/` を tar.gz スナップショット。直近 `keep` 世代だけ残す。"""
    snap_dir = company_dir / "skills" / ".snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    name = f"skills-{dt.date.today().strftime('%Y-%m-%d')}.tar.gz"
    path = snap_dir / name
    skills_dir = company_dir / "skills"
    with tarfile.open(path, "w:gz") as tar:
        for entry in skills_dir.iterdir():
            if entry.name == ".snapshots":
                continue
            tar.add(entry, arcname=f"skills/{entry.name}")
    snaps = sorted(snap_dir.glob("skills-*.tar.gz"))
    for old in snaps[:-keep]:
        old.unlink(missing_ok=True)


def _recent_skill_hits(skill_hits_path: Path, days: int = 90) -> list[str]:
    """直近 `days` 日に1回以上ヒットしたスキル名の一覧。"""
    if not skill_hits_path.exists():
        return []
    cutoff = (dt.date.today() - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    hits = set()
    for ln in skill_hits_path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if rec.get("date", "") >= cutoff:
            hits.add(rec.get("skill", ""))
    return sorted(h for h in hits if h)


def _skill_overview(company_dir: Path, max_head_chars: int = 600) -> str:
    skills_dir = company_dir / "skills"
    lines = []
    if not skills_dir.exists():
        return "(skills ディレクトリなし)"
    for entry in sorted(skills_dir.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_file() and entry.suffix == ".md":
            lines.append(f"### skills/{entry.name}\n" + entry.read_text(encoding="utf-8")[:max_head_chars])
        elif entry.is_dir() and (entry / "SKILL.md").exists():
            lines.append(f"### skills/{entry.name}/SKILL.md\n" + (entry / "SKILL.md").read_text(encoding="utf-8")[:max_head_chars])
    return "\n\n".join(lines)


CURATOR_PERSONA = """あなたは TrustLink のスキルキュレーターです。12名のAI社員のような人格は持ちません。
`.company/skills/` の健全性を保つことだけが仕事です。ファイルの Read/Write/Edit/Glob/Grep のみ使えます。
削除は決してしてはいけません（アーカイブ＝`.company/skills/.archive/` への移動のみ）。判断に迷ったら触らないでください。"""


def build_curator_prompt(skill_overview: str, recent_hits: list[str]) -> str:
    hits_str = ", ".join(recent_hits) if recent_hits else "(記録なし)"
    return f"""`.company/skills/` 全体を棚卸ししてください。やることは次の3つだけです。
1. 内容が重なる狭いスキルを「クラスレベルの包括スキル」に統合する（元スキルの手順・品質チェックリスト・失敗時の対応を取りこぼさず織り込み、元ファイルは `.company/skills/.archive/` へ移動）。
2. 明らかに陳腐化・未使用のスキルを `.company/skills/.archive/` に移動する（削除ではなく移動）。
3. frontmatter（`name` / `owner` / `trigger`）が崩れているものを直す。

制約:
- 削除は絶対にしない。アーカイブ＝移動のみ。
- 迷ったら触らない（保守的に）。
- 1回の棚卸しで触るスキルは最大5件まで。残りは来週。
- スキル本文が長くなりすぎているもの（概ね80-100行超）は、骨子だけ `<name>/SKILL.md` に残し、詳細・長いサンプル・チェックリストを `<name>/references/*.md` に分ける形に整形してよい。
- `.company/skills/README.md` のスキル一覧も実態に合わせて更新する。

参考: 直近90日に1回以上参照されたスキル: {hits_str}（記録に無い＝最近使われていない候補。ただし即アーカイブの根拠にはしない。判断材料に留める）

## 現在のスキル一覧（各冒頭）
{skill_overview}

---
作業が終わったら、最後に1つだけ次の形式で `<summary>` を返してください:
`<summary>before=<件数> after=<件数> merged=[...] archived=[...] created=[...] fixed=[...]</summary>`
"""


def run_curation(
    company_dir: Path,
    model: str,
    skill_hits_path: Path,
    *,
    allowed_tools: str = "Read Write Edit Glob Grep",
    disallowed_tools: str = "Bash WebFetch WebSearch Task",
    max_turns: int = 25,
    timeout_sec: int = 600,
    snapshot_keep: int = 8,
) -> dict:
    """戻り値: {status, note, summary, head_before, out_of_bounds}."""
    head_before = cli_runner.git_head(company_dir)
    try:
        _make_snapshot(company_dir, keep=snapshot_keep)
    except Exception:  # noqa: BLE001
        logger.exception("skills スナップショット作成に失敗（処理は続行）")

    overview = _skill_overview(company_dir)
    hits = _recent_skill_hits(skill_hits_path)
    prompt = build_curator_prompt(overview, hits)
    result = cli_runner.run_claude(
        prompt=prompt, cwd=company_dir, model=model,
        allowed_tools=allowed_tools, disallowed_tools=disallowed_tools,
        system_prompt_append=CURATOR_PERSONA, max_turns=max_turns, timeout_sec=timeout_sec,
    )

    status_lines = cli_runner.git_status_short(company_dir)
    # キュレーターは skills/ と skills/.archive/ のみ許可（DEPT_KNOWLEDGE は対象外）
    oob = []
    for ln in status_lines:
        p = cli_runner.parse_status_path(ln)
        if not (p.startswith("skills/")):
            oob.append(p)
    if oob:
        cli_runner.git_checkout_paths(company_dir, oob)
        logger.warning("curator touched out-of-bounds paths, reverted: %s", oob)

    if result.timed_out:
        return {"status": "error", "note": "timeout", "summary": "", "head_before": head_before, "out_of_bounds": oob}
    if not result.ok:
        return {"status": "error", "note": f"exit={result.returncode}: {result.stderr[-300:]}",
                "summary": "", "head_before": head_before, "out_of_bounds": oob}
    summary = _parse_summary(result.stdout)
    if summary is None:
        return {"status": "error", "note": "no_summary", "summary": "", "head_before": head_before, "out_of_bounds": oob}
    return {"status": "done", "note": "", "summary": summary, "head_before": head_before, "out_of_bounds": oob}
```

- [ ] **Step 4: 実行して通ることを確認**

Run: `cd products/d-manager && python -m pytest tests/test_learning_curator.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add products/d-manager/learning/curator.py products/d-manager/tests/test_learning_curator.py
git commit -m "feat(d-manager): learning curator（週次スキル棚卸し）"
```

---

## Task 12: scheduler.py — learning_review ジョブと weekly_review への curator/prune 追加

**Files:**
- Modify: `products/d-manager/scheduler.py`

（スケジューラの実行は live discord に依存するためユニットテストは置かず、import スモークで担保。`learning_review` 本体のロジックは Task 3–11 でテスト済みの関数を呼ぶだけにする。）

- [ ] **Step 1: scheduler.py に学習ループ用の関数を追加**

`scheduler.py` の適当な場所（他の `async def ...review()` の近く）に、次の関数を追加する。Discord 送信は、このファイル内で既に使われているチャンネル投稿ヘルパに合わせる（例: `morning_briefing` が使っている送信関数。ここでは仮に `send_to_channel(channel_name: str, text: str)` とする — 実際の名前に置き換えること）:
```python
async def learning_review():
    """夜間バッチ: 未レビューのセッション（チャンネル+日付）を振り返り、.company/ を更新する。"""
    import config
    if not config.LEARNING_REVIEW_ENABLED:
        logger.info("learning_review: disabled (LEARNING_REVIEW_ENABLED=false), skip")
        return
    logger.info("Running learning_review...")
    from learning import store, reviewer

    db = config.LEARNING_DB_PATH
    company = config.COMPANY_DIR
    store.init_db(db)
    requeued = store.requeue_stuck(db, stuck_minutes=config.LEARNING_STUCK_MINUTES)
    if requeued:
        logger.info("learning_review: requeued %d stuck sessions", requeued)
    skipped = store.mark_short_skipped(db, min_turns=config.LEARNING_MIN_TURNS)
    pending = store.list_pending_reviews(
        db, min_turns=config.LEARNING_MIN_TURNS, max_age_days=config.LEARNING_REVIEW_MAX_AGE_DAYS
    )[: config.LEARNING_MAX_PER_RUN]

    results = []
    for sess in pending:
        try:
            res = reviewer.run_review(
                db_path=db, company_dir=company,
                channel_id=sess["channel_id"], review_date=sess["review_date"],
                channel_name=sess.get("channel_name") or sess["channel_id"],
                department=sess.get("department") or "secretary",
                model=config.REVIEW_MODEL_CLI, dryrun=config.LEARNING_REVIEW_DRYRUN,
                allowed_tools=config.LEARNING_ALLOWED_TOOLS,
                dryrun_allowed_tools=config.LEARNING_DRYRUN_ALLOWED_TOOLS,
                disallowed_tools=config.LEARNING_DISALLOWED_TOOLS,
                char_limit=config.LEARNING_CONTEXT_CHAR_LIMIT,
                timeout_sec=config.LEARNING_REVIEW_TIMEOUT_SEC,
                skill_hits_path=config.SKILL_HITS_PATH,
            )
            results.append((sess, res))
        except Exception:  # noqa: BLE001
            logger.exception("learning_review: run_review failed for %s/%s",
                             sess["channel_id"], sess["review_date"])
            results.append((sess, {"status": "error", "note": "exception", "out_of_bounds": []}))

    # 通知メッセージを組み立て
    n = len(results)
    with_learning = sum(1 for _, r in results if r["status"] == "done" and not r["note"].startswith("no_learnings"))
    errors = sum(1 for _, r in results if r["status"] == "error")
    oob_any = [p for _, r in results for p in r.get("out_of_bounds", [])]
    mode = "ドライラン" if config.LEARNING_REVIEW_DRYRUN else "本番"
    lines = [f"🧠 **今夜の学習ラン**（{mode}）: {n}件レビュー / {with_learning}件で学びあり / エラー{errors}件 / skipped(too_short){skipped}件"]
    for sess, r in results:
        tag = "📝" if (r["status"] == "done" and not r["note"].startswith("no_learnings")) else ("⚠️" if r["status"] == "error" else "—")
        lines.append(f"{tag} {sess.get('channel_name') or sess['channel_id']} ({sess['review_date']}): {r['note'][:200]}")
    if oob_any:
        lines.append(f"🚨 範囲外への書き込みを検出し revert しました: {oob_any}")
    try:
        await send_to_channel(config.LEARNING_NOTIFY_CHANNEL, "\n".join(lines))
    except Exception:  # noqa: BLE001
        logger.exception("learning_review: notify failed")
    logger.info("learning_review done: %s", lines[0])


async def learning_curate():
    """週次キュレーター（weekly_review から呼ばれる、または !learning curate）。"""
    import config
    logger.info("Running learning_curate...")
    from learning import curator
    res = curator.run_curation(
        company_dir=config.COMPANY_DIR, model=config.CURATOR_MODEL_CLI,
        skill_hits_path=config.SKILL_HITS_PATH,
        disallowed_tools=config.LEARNING_DISALLOWED_TOOLS,
        timeout_sec=config.LEARNING_CURATOR_TIMEOUT_SEC,
    )
    if res["status"] == "done":
        msg = (f"🧹 **今週のスキル棚卸し**: {res['summary']}\n"
               f"（巻き戻し基準コミット: `{res['head_before'][:10]}` — やりすぎなら `git -C .company revert` 可）")
    else:
        msg = f"⚠️ スキル棚卸しに失敗: {res['note']}（スナップショット `.company/skills/.snapshots/` から復元可）"
    if res.get("out_of_bounds"):
        msg += f"\n🚨 範囲外書き込みを revert: {res['out_of_bounds']}"
    try:
        await send_to_channel(config.LEARNING_NOTIFY_CHANNEL, msg)
    except Exception:  # noqa: BLE001
        logger.exception("learning_curate: notify failed")
    logger.info("learning_curate done: %s", res.get("summary") or res.get("note"))


def learning_prune():
    """会話ログの保持期間プルーニング（weekly_review から同期呼び出し）。"""
    import config
    from learning import store
    try:
        deleted = store.prune(config.LEARNING_DB_PATH, retention_days=config.TURNS_RETENTION_DAYS)
        logger.info("learning_prune: deleted %d old turns", deleted)
    except Exception:  # noqa: BLE001
        logger.exception("learning_prune failed")
```

- [ ] **Step 2: `weekly_review()` の末尾に curator と prune を呼ぶ**

`scheduler.py` の `async def weekly_review():` の本体の最後（既存の週次レビュー処理が終わった後）に追加:
```python
    # 学習ループ: スキル棚卸し + 会話ログのプルーニング
    learning_prune()
    try:
        await learning_curate()
    except Exception:  # noqa: BLE001
        logger.exception("weekly_review: learning_curate failed")
```

- [ ] **Step 3: スケジューラ起動部に learning_review ジョブを登録**

`scheduler.py` 末尾の `_scheduler.add_job(...)` 群（`weekly_review` を登録しているあたり）に追加:
```python
    _scheduler.add_job(
        learning_review,
        "cron",
        hour=config.LEARNING_REVIEW_HOUR,
        minute=0,
        id="learning_review",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
```
（`config` はこのファイルで既に import 済みのはず。`from apscheduler...` の hour/minute は他のジョブの書き方に合わせる。）

- [ ] **Step 4: ジョブ例外ハンドラの確認**

`_scheduler = AsyncIOScheduler(...)` の生成箇所を見て、`EVENT_JOB_ERROR` リスナーが既にあるか確認する。無ければ追加:
```python
from apscheduler.events import EVENT_JOB_ERROR

def _on_job_error(event):
    logger.error("Scheduler job %s raised: %s", event.job_id, event.exception)
    # learning_review/learning_curate の失敗は Discord にも通知（best-effort）
    if event.job_id in ("learning_review", "learning_curate", "weekly_review"):
        try:
            import asyncio, config
            asyncio.get_event_loop().create_task(
                send_to_channel(config.LEARNING_NOTIFY_CHANNEL, f"⚠️ スケジューラジョブ `{event.job_id}` が例外: {event.exception}")
            )
        except Exception:  # noqa: BLE001
            pass

# _scheduler 生成後:
_scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)
```
（既存のエラーリスナーがあるなら、そこに `learning_*` の Discord 通知だけ足す。）

- [ ] **Step 5: import スモーク**

Run: `cd products/d-manager && python -c "import scheduler; print('scheduler import ok')"`
Expected: `scheduler import ok`

- [ ] **Step 6: Commit**

```bash
git add products/d-manager/scheduler.py
git commit -m "feat(d-manager): scheduler に learning_review(23:00) と weekly の curator/prune"
```

---

## Task 13: main.py — !session reset で即レビュー / !learning コマンド群 / notify ヘルパ

**Files:**
- Modify: `products/d-manager/main.py`

- [ ] **Step 1: main.py に学習ループ用のヘルパと即レビュー呼び出しを追加**

`main.py` の適当な場所（他のヘルパ関数の近く）に追加:
```python
def notify_learning_alert(text: str) -> None:
    """ai_engine 等から呼ばれる同期版アラート（best-effort、event loop があれば投げる）。"""
    try:
        import asyncio
        import config
        loop = asyncio.get_event_loop()
        loop.create_task(send_to_channel(config.LEARNING_NOTIFY_CHANNEL, text))
    except Exception:  # noqa: BLE001
        pass


async def _kick_review_for_channel(channel_id: str, channel_name: str) -> str:
    """指定チャンネルの「今日のセッション」を即レビューする（!session reset / !learning review 用）。
    バックグラウンドスレッドで run_review を回し、結果文字列を返す。"""
    import datetime as dt
    import asyncio
    import config
    from learning import store, reviewer
    from departments import get_department_for_channel

    today = dt.date.today().strftime("%Y-%m-%d")
    store.init_db(config.LEARNING_DB_PATH)
    row = store.get_session_row(config.LEARNING_DB_PATH, str(channel_id), today)
    if not row or row["turn_count"] < 1:
        return "（今日このチャンネルに記録された会話がないため、レビューはスキップしました）"
    department = get_department_for_channel(channel_name) if channel_name else "secretary"

    def _do():
        return reviewer.run_review(
            db_path=config.LEARNING_DB_PATH, company_dir=config.COMPANY_DIR,
            channel_id=str(channel_id), review_date=today,
            channel_name=channel_name or str(channel_id), department=department,
            model=config.REVIEW_MODEL_CLI, dryrun=config.LEARNING_REVIEW_DRYRUN,
            allowed_tools=config.LEARNING_ALLOWED_TOOLS,
            dryrun_allowed_tools=config.LEARNING_DRYRUN_ALLOWED_TOOLS,
            disallowed_tools=config.LEARNING_DISALLOWED_TOOLS,
            char_limit=config.LEARNING_CONTEXT_CHAR_LIMIT,
            timeout_sec=config.LEARNING_REVIEW_TIMEOUT_SEC,
            skill_hits_path=config.SKILL_HITS_PATH,
        )

    res = await asyncio.get_event_loop().run_in_executor(None, _do)
    mode = "ドライラン" if config.LEARNING_REVIEW_DRYRUN else "本番"
    out = f"🧠 即レビュー（{mode}）完了: {res['status']} — {res['note'][:300]}"
    if res.get("out_of_bounds"):
        out += f"\n🚨 範囲外書き込みを revert: {res['out_of_bounds']}"
    return out
```

- [ ] **Step 2: `!session reset` の処理に即レビュー呼び出しを足す**

`main.py` の `if raw.startswith("!session"):` ブロック内、`reset` を処理してセッションを消した直後に追加:
```python
        # （既存の reset 処理: ai_engine.reset_cli_session(...) などの後）
        if config.LEARNING_REVIEW_ENABLED:
            await send_as_character_with_avatar(message.channel, "🧠 直前の会話を学習レビューします…", channel_name)
            try:
                msg = await _kick_review_for_channel(str(message.channel.id), channel_name)
            except Exception as e:  # noqa: BLE001
                msg = f"（学習レビューでエラー: {e}）"
            await send_as_character_with_avatar(message.channel, msg, channel_name)
```
（`config` を main.py が import していなければ `import config` を先頭に追加。`channel_name` は既にこのスコープにある想定 — 無ければ `get_department_for_channel` を呼んでいる箇所から取る。）

- [ ] **Step 3: `!learning` コマンド群を追加**

`main.py` の `on_message` 内、`if raw.startswith("!run"):` の分岐の近くに新しい分岐を追加:
```python
    # Quick command: !learning <subcommand>
    if raw.startswith("!learning"):
        import config
        from learning import store
        import departments
        parts = raw.split(maxsplit=2)
        sub = parts[1] if len(parts) >= 2 else "status"
        arg = parts[2] if len(parts) >= 3 else ""
        db = config.LEARNING_DB_PATH
        store.init_db(db)

        if sub == "status":
            import datetime as dt
            pending = store.list_pending_reviews(db, min_turns=config.LEARNING_MIN_TURNS,
                                                 max_age_days=config.LEARNING_REVIEW_MAX_AGE_DAYS)
            # 直近のレビュー結果サマリ（done/error/skipped の件数と no_learnings 率）
            # ※ 簡易集計: sessions テーブルを直接読む
            import sqlite3
            conn = sqlite3.connect(str(db)); conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT review_status, review_note FROM sessions WHERE reviewed_at IS NOT NULL "
                                "ORDER BY reviewed_at DESC LIMIT 100").fetchall()
            conn.close()
            done = sum(1 for r in rows if r["review_status"] == "done")
            err = sum(1 for r in rows if r["review_status"] == "error")
            skip = sum(1 for r in rows if r["review_status"] == "skipped")
            no_learn = sum(1 for r in rows if r["review_status"] == "done" and (r["review_note"] or "").startswith("no_learnings"))
            metrics = departments.skills_concat_size()
            bloat = ""
            if metrics["concat_chars"] >= config.SKILL_BLOAT_CHAR_THRESHOLD or metrics["count"] >= config.SKILL_BLOAT_COUNT_THRESHOLD:
                bloat = f"\n⚠️ スキルライブラリが膨らんでいます（{metrics['count']}件 / {metrics['concat_chars']}文字）。Tier B（SKILL.md化・progressive disclosure）の検討時期です。"
            mode = "ドライラン" if config.LEARNING_REVIEW_DRYRUN else ("本番" if config.LEARNING_REVIEW_ENABLED else "無効(観測のみ)")
            await send_as_character_with_avatar(message.channel,
                f"🧠 **学習ループ状態**（{mode}）\n"
                f"- 未レビュー: {len(pending)}件\n"
                f"- 直近100件: done {done} / error {err} / skipped {skip} / うち no_learnings {no_learn}（学び率 {(done-no_learn)}/{max(done,1)}）\n"
                f"- スキル: {metrics['count']}件 / 連結 {metrics['concat_chars']}文字{bloat}",
                channel_name)
            return

        if sub in ("review", "retry"):
            # !learning review / !learning review <channel_name> / !learning retry <channel_name> <date>
            target_name = arg.split()[0] if arg else channel_name
            target_id = str(message.channel.id) if (not arg or target_name == channel_name) else None
            if target_id is None:
                # channel_name から channel オブジェクトを探す
                ch = discord.utils.get(message.guild.text_channels, name=target_name) if message.guild else None
                target_id = str(ch.id) if ch else None
            if target_id is None:
                await send_as_character_with_avatar(message.channel, f"⚠️ チャンネル `{target_name}` が見つかりません。", channel_name)
                return
            if sub == "retry":
                # retry はエラー終了したセッションを未レビューに戻してから即レビュー
                tokens = arg.split()
                rdate = tokens[1] if len(tokens) >= 2 else __import__("datetime").date.today().strftime("%Y-%m-%d")
                import sqlite3
                conn = sqlite3.connect(str(db))
                conn.execute("UPDATE sessions SET review_status=NULL, reviewed_at=NULL, review_note=NULL "
                             "WHERE channel_id=? AND review_date=? AND review_status='error'", (target_id, rdate))
                conn.commit(); conn.close()
            await send_as_character_with_avatar(message.channel, "🧠 即レビューを実行します…", channel_name)
            msg = await _kick_review_for_channel(target_id, target_name)
            await send_as_character_with_avatar(message.channel, msg, channel_name)
            return

        if sub == "search":
            if not arg:
                await send_as_character_with_avatar(message.channel, "使い方: `!learning search <キーワード>`", channel_name)
                return
            hits = store.search(db, arg, limit=20)
            if not hits:
                await send_as_character_with_avatar(message.channel, f"「{arg}」に一致する会話はありませんでした。", channel_name)
                return
            lines = [f"🔎 「{arg}」 {len(hits)}件:"]
            for h in hits[:20]:
                snippet = (h["content"][:120] + "…") if len(h["content"]) > 120 else h["content"]
                lines.append(f"- [{h['ts'][:16]}] {h.get('channel_name') or '?'} ({h['role']}): {snippet}")
            await send_as_character_with_avatar(message.channel, "\n".join(lines)[:1900], channel_name)
            return

        if sub == "curate":
            await send_as_character_with_avatar(message.channel, "🧹 スキル棚卸しを実行します（数分かかります）…", channel_name)
            from scheduler import learning_curate
            try:
                await learning_curate()
                await send_as_character_with_avatar(message.channel, "✅ 棚卸し完了（結果は通知チャンネルに投稿しました）。", channel_name)
            except Exception as e:  # noqa: BLE001
                await send_as_character_with_avatar(message.channel, f"⚠️ 棚卸しでエラー: {e}", channel_name)
            return

        if sub == "healthcheck":
            # ダミー会話を入れて dryrun レビューを即実行し、<summary> が返るか確認
            import datetime as dt
            today = dt.date.today().strftime("%Y-%m-%d")
            hc_chan = "healthcheck-temp"
            store.record_turn(db, hc_chan, "healthcheck", "secretary", "hc-sess", "user", "これはヘルスチェックの会話です", "cli", "chat", True)
            store.record_turn(db, hc_chan, "healthcheck", "secretary", "hc-sess", "assistant", "了解しました", "cli", "chat", True)
            from learning import reviewer
            import asyncio
            res = await asyncio.get_event_loop().run_in_executor(None, lambda: reviewer.run_review(
                db_path=db, company_dir=config.COMPANY_DIR, channel_id=hc_chan, review_date=today,
                channel_name="healthcheck", department="secretary", model=config.REVIEW_MODEL_CLI,
                dryrun=True, timeout_sec=config.LEARNING_REVIEW_TIMEOUT_SEC))
            ok = res["status"] in ("done", "error") and res["status"] != "error"
            # healthcheck の sessions/turns 行は残ってもよい（reviewable=True だが review済みなので拾われない）が、片付けたいなら削除:
            import sqlite3
            conn = sqlite3.connect(str(db))
            conn.execute("DELETE FROM turns WHERE channel_id=?", (hc_chan,))
            conn.execute("DELETE FROM sessions WHERE channel_id=?", (hc_chan,))
            conn.commit(); conn.close()
            await send_as_character_with_avatar(message.channel,
                f"🩺 学習ループ疎通確認: {'✅ OK' if res['status']!='error' else '❌ NG'} — {res['status']}: {res['note'][:200]}", channel_name)
            return

        await send_as_character_with_avatar(message.channel,
            "🧠 **!learning コマンド**\n"
            "- `!learning status` — 状態（未レビュー数・学び率・スキル肥大）\n"
            "- `!learning review [チャンネル名]` — 即レビュー\n"
            "- `!learning retry <チャンネル名> [YYYY-MM-DD]` — エラー終了したレビューを再試行\n"
            "- `!learning search <キーワード>` — 過去会話を検索\n"
            "- `!learning curate` — スキル棚卸しを今すぐ実行\n"
            "- `!learning healthcheck` — 疎通確認", channel_name)
        return
```

注: 上記は `discord` / `send_as_character_with_avatar` / `channel_name` / `message` が `on_message` スコープで使える前提。実コードに合わせて変数名を調整すること。長い `send_as_character_with_avatar` の本文は Discord の2000文字制限に注意（`[:1900]` で切るなどは入れてある）。

- [ ] **Step 4: import スモークと文法チェック**

Run: `cd products/d-manager && python -c "import main; print('main import ok')"`
Expected: `main import ok`（循環 import が無いこと。`from scheduler import learning_curate` 等は関数内 import にしてあるので OK のはず）

Run: `cd products/d-manager && python -m py_compile main.py && echo "syntax ok"`
Expected: `syntax ok`

- [ ] **Step 5: Commit**

```bash
git add products/d-manager/main.py
git commit -m "feat(d-manager): !learning コマンド群と !session reset 即レビュー・notify ヘルパ"
```

---

## Task 14: 全テスト実行 & 起動スモーク & ロールアウト確認

**Files:**
- （変更なし。確認のみ。必要なら README/runbook に追記）

- [ ] **Step 1: 全ユニットテストを実行**

Run: `cd products/d-manager && python -m pytest tests/ -q`
Expected: すべて pass（store 10 + reviewer 9 + curator 3 + departments 3 = 25 件前後）。失敗があれば修正してから次へ。

- [ ] **Step 2: bot 起動スモーク（ドライ起動）**

Run: `cd products/d-manager && python -c "import main, scheduler, ai_engine, departments, flows; from learning import store, reviewer, curator, cli_runner; print('all modules import ok')"`
Expected: `all modules import ok`

可能なら実際に bot を短時間起動して例外なくスケジューラが立ち上がることを確認（環境変数・トークンが要るので、ユーザーに依頼してもよい）:
Run: `cd products/d-manager && timeout 15 python main.py 2>&1 | tail -20`
Expected: 「scheduler started」「Loaded N CLI sessions」等のログが出て、`learning_review` ジョブが登録され、例外で落ちないこと（`LEARNING_REVIEW_ENABLED=false` なので learning_review は何もしない）。

- [ ] **Step 3: Phase 1（観測のみ）の状態であることを確認**

Run: `cd products/d-manager && python -c "import config; print('ENABLED=', config.LEARNING_REVIEW_ENABLED, 'DRYRUN=', config.LEARNING_REVIEW_DRYRUN)"`
Expected: `ENABLED= False DRYRUN= True` — つまりデプロイしても会話ログは溜まるがレビューは動かない（Phase 1）。Phase 2 へは launchd の環境変数（または `.env`）に `LEARNING_REVIEW_ENABLED=true`（DRYRUN は true のまま）を足す。Phase 3 は `LEARNING_REVIEW_DRYRUN=false` も足す。Phase 4（キュレーター）は weekly_review が自動で呼ぶので追加操作不要。— この手順を `products/d-manager/docs/specs/2026-05-12-learning-loop-design.md` の §5 ロールアウトに既に記載済み。

- [ ] **Step 4: 設計ドキュメントとの突合（self-review）**

`products/d-manager/docs/specs/2026-05-12-learning-loop-design.md` を開き、§1〜§7 の各要件にこのプランのどのタスクが対応するかを確認する。主な対応:
- §1 データモデル → Task 3,4,5（store.py）
- §1 書き込み点（ai_engine 侵襲）→ Task 9
- §1 agent-call/council の reviewable=False → Task 9 の `_learning_origin()` が `scheduler-*` と `agent-call-*` を両方 `reviewable=False` にする（council は council 専用フローが使うチャンネルで動くが、人手の議論なのでレビュー対象でよい — synthetic でない通常チャンネルなら `chat`/reviewable=True のまま）
- §2 発火フロー → Task 12（learning_review）, Task 13（!session reset 即レビュー, !learning コマンド）
- §2 フロー完了時登録 → **未実装**。flows.py の `run_flow` 末尾でそのフローが使ったチャンネルの sessions 行に何かする必要があるが、flows が `process_message` に渡す channel 識別子の実態確認が要る。本プランでは省略しているので、必要なら追加タスクとして flows.py に「`if ok:` の後、`_run_step` が使った channel_id をキーに `store` で reviewable を確実に True にする（既定 True なので実質 no-op の場合が多い）」を入れる。**最小実装としては省略可**（チャットで使ったチャンネルは既に reviewable=True で記録されているため、フロー完了時の特別扱いが本当に要るのは「フロー専用の synthetic channel」を使っている場合のみ）。
- §3 レビュープロンプト/書き込み先/モデル → Task 7,8,12
- §4 キュレーター → Task 11,12
- §4.5 肥大メトリクス + references/ デュアルローダー → Task 5（skill_metrics）, Task 10（departments）, Task 13（!learning status）
- §5 エラー処理/テスト/ロールアウト → Task 8,12,13（エラー処理）, 各 Task のテスト, Task 14（ロールアウト確認）
- §6 ファイル一覧 → 本プランの「ファイル構成」と一致
- §7 元記事との対応 → 実装には影響しない（説明のみ）

ギャップとして残るのは「§2 フロー完了時登録」のみ（Task は本プランに無い）。最小実装では省略可（理由は上記）。agent-call channel の reviewable=False は Task 9 の `_learning_origin()` で対応済み。

- [ ] **Step 5: Commit（もし self-review で何か直したら）**

```bash
git add -A products/d-manager
git commit -m "chore(d-manager): 学習ループ self-review 反映（agent-call channel を reviewable=False ほか）"
```

---

## 完了条件

- `cd products/d-manager && python -m pytest tests/ -q` が全 pass
- `python main.py` が例外なく起動し、scheduler に `learning_review` ジョブが登録される
- `LEARNING_REVIEW_ENABLED=false`（Phase 1）の状態でデプロイ可能 — 会話ログ `learning/conversations.db` が溜まり始める
- `!learning status` が Discord で動く
- Phase 2 以降は環境変数（`.env` / launchd plist）の切り替えだけで進められる

## 次のサイクル（このプランの対象外）

- 「フロー完了時のレビュー登録」を flows.py に正式実装（synthetic channel を使うフロー用）
- Tier B 本体: `.company/skills/*.md` の一括 `<name>/SKILL.md` 化、progressive disclosure の本格運用、`.usage.json` 利用統計、審査ゲート付き外部スキル tap
- Tier A: モデルフォールバックルーター、`<PROVIDER>_API_KEY_1..N` ローテーション
- メモリ自動注入サイクル: `_build_system_prompt` への「現在のメモリ要約」凍結注入、文字数上限での自己統合、`tools/memory.py` の API tool 化
