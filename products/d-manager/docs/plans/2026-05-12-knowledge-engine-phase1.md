# 知見エンジン フェーズ1（チャット→議事録化）実装プラン

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** d-manager の各チャンネル/councilスレッドの会話を日次で構造化議事録（SQLite `knowledge.db` + Markdownビュー）にする夜間バッチを追加する。

**Architecture:** 新モジュール `knowledge/`（`learning/` と並列）。生データは既存 `learning/store.py` の `turns`/`sessions` テーブルを読むだけ。`knowledge/digest.py` がセッションごとに `claude -p`（`learning/cli_runner.run_claude`）で議事録化し、`knowledge/store.py` に保存＋`knowledge/views.py` で `.company/secretary/knowledge/digests/` にMarkdown書き出し。`scheduler.py` に夜間ジョブ `knowledge_digest` を追加（`learning_review`(23:00) の後・23:30）。`main.py` に `!digest` コマンド。`scheduler.morning_briefing` に1行サマリ。

**Tech Stack:** Python 3.x（d-manager は `from __future__ import annotations` 前提・型ヒント可）、SQLite WAL + FTS5(trigram)、APScheduler(cron)、pytest（`tmp_path` で一時DB、`monkeypatch` で `claude -p` をモック）。

**Spec:** `products/d-manager/docs/specs/2026-05-12-knowledge-engine-design.md` の §3 がこのプランの対象範囲。§4〜7 は対象外（後続フェーズで別プラン）。

---

## ファイル構成

| パス | 役割 | 新規/変更 |
|---|---|---|
| `products/d-manager/knowledge/__init__.py` | パッケージマーカー（空） | 新規 |
| `products/d-manager/knowledge/store.py` | SQLite `knowledge.db`: `digests` テーブル + FTS5 + `init_db`/`upsert_digest`/`get_digests`/`search` | 新規 |
| `products/d-manager/knowledge/digest.py` | 議事録化プロンプト組み立て + `build_daily_digests(date)` + `index_council_meetings(date)` | 新規 |
| `products/d-manager/knowledge/views.py` | `write_digest_md(...)` — `knowledge.db` の1 digest を Markdown で `.company/secretary/knowledge/digests/` に書く | 新規 |
| `products/d-manager/learning/store.py` | `list_sessions_for_date(db_path, date, min_turns)` を追加（既存 `list_pending_reviews` の SQL 流用） | 変更 |
| `products/d-manager/config.py` | `KNOWLEDGE_DIR` / `KNOWLEDGE_DB_PATH` / `KNOWLEDGE_VIEW_DIR` / `KNOWLEDGE_DIGEST_ENABLED` / `KNOWLEDGE_DIGEST_HOUR` / `KNOWLEDGE_DIGEST_MINUTE` / `KNOWLEDGE_MIN_DIGEST_TURNS` / `KNOWLEDGE_DIGEST_TIMEOUT_SEC` / `KNOWLEDGE_DIGEST_MAX_SESSIONS` / `KNOWLEDGE_NOTIFY_CHANNEL` / `KNOWLEDGE_NOTIFICATION_CHANNEL_IDS` を追加 | 変更 |
| `products/d-manager/scheduler.py` | `async def knowledge_digest()` 追加 + `_scheduler.add_job(...)` 登録 + `morning_briefing()` 末尾に1行サマリ | 変更 |
| `products/d-manager/main.py` | `!digest [YYYY-MM-DD]` コマンド処理 | 変更 |
| `products/d-manager/.company/.gitignore` | `secretary/knowledge/` を ignore（Markdownビューはコミットしない＝SQLiteが正） | 新規 |
| `products/d-manager/tests/test_knowledge_store.py` | `store.py` のテスト | 新規 |
| `products/d-manager/tests/test_knowledge_digest.py` | `digest.py` のテスト（`run_claude` モック） | 新規 |
| `products/d-manager/tests/test_knowledge_views.py` | `views.py` のテスト | 新規 |
| `products/d-manager/tests/test_learning_store.py` | `list_sessions_for_date` のテストを追記 | 変更 |

> 注: `.gitignore`（`products/d-manager/.gitignore`）は既に `*.db` を含むので `knowledge.db` は追加不要。

> 注: ターン整形は既存 `learning.reviewer.format_conversation_log(channel_name, department, review_date, turns, char_limit)` をそのまま import して使う（新規切り出し不要）。

> 作業ディレクトリは `products/d-manager/`。以下、`pytest` 等のコマンドはこのディレクトリで実行する想定（`cd products/d-manager` 済み、または絶対パス）。コミットは `git -C /Users/Mac_air/Claude-Workspace` で行ってもよいが、以下では簡潔さのためリポジトリルートで `git add <相対パス>` する形で書く。

---

## Task 1: config に knowledge 設定を追加

**Files:**
- Create: `products/d-manager/knowledge/__init__.py`
- Modify: `products/d-manager/config.py`（末尾の `# ── Learning loop ──` ブロックの直後に追記）

- [ ] **Step 1: `knowledge/__init__.py` を作成（空ファイル）**

```python
```
（中身は空でよい。`learning/__init__.py` と同じ。）

- [ ] **Step 2: `config.py` に設定を追記**

`config.py` の末尾（最後の行 `LEARNING_DISALLOWED_TOOLS = ...` の下）に以下を追加する。`COMPANY_DIR` は config.py 冒頭で既に定義済み。`import os` / `from pathlib import Path` も既にあるので不要。

```python

# ── Knowledge engine（フェーズ1: 議事録化）─────────────────────────────────
KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"
KNOWLEDGE_DB_PATH = Path(
    os.getenv("KNOWLEDGE_DB_PATH", str(KNOWLEDGE_DIR / "knowledge.db"))
)
# Markdownビューの出力先（.company 配下・別gitリポ。.company/.gitignore で secretary/knowledge/ を除外）
KNOWLEDGE_VIEW_DIR = COMPANY_DIR / "secretary" / "knowledge"

# 安全弁: デフォルト無効。テスト後に KNOWLEDGE_DIGEST_ENABLED=true で本番化。
KNOWLEDGE_DIGEST_ENABLED = (
    os.getenv("KNOWLEDGE_DIGEST_ENABLED", "false").lower() == "true"
)
KNOWLEDGE_DIGEST_HOUR = int(os.getenv("KNOWLEDGE_DIGEST_HOUR", "23"))
KNOWLEDGE_DIGEST_MINUTE = int(os.getenv("KNOWLEDGE_DIGEST_MINUTE", "30"))
KNOWLEDGE_MIN_DIGEST_TURNS = int(os.getenv("KNOWLEDGE_MIN_DIGEST_TURNS", "4"))
KNOWLEDGE_DIGEST_TIMEOUT_SEC = int(os.getenv("KNOWLEDGE_DIGEST_TIMEOUT_SEC", "180"))
KNOWLEDGE_DIGEST_MAX_SESSIONS = int(os.getenv("KNOWLEDGE_DIGEST_MAX_SESSIONS", "20"))
KNOWLEDGE_NOTIFY_CHANNEL = os.getenv("KNOWLEDGE_NOTIFY_CHANNEL", "日報-daily-digest")

# 議事録化の対象から外す通知専用チャンネル。channel_id ベースで除外する。
# 環境変数 KNOWLEDGE_NOTIFICATION_CHANNEL_IDS にカンマ区切りの Discord channel_id を入れる。未設定なら空。
KNOWLEDGE_NOTIFICATION_CHANNEL_IDS = tuple(
    cid.strip()
    for cid in os.getenv("KNOWLEDGE_NOTIFICATION_CHANNEL_IDS", "").split(",")
    if cid.strip()
)
```

- [ ] **Step 3: import が通ることを確認**

Run: `cd products/d-manager && python -c "import config; print(config.KNOWLEDGE_DB_PATH, config.KNOWLEDGE_DIGEST_ENABLED, config.KNOWLEDGE_MIN_DIGEST_TURNS)"`
Expected: `.../knowledge/knowledge.db False 4` のような行が表示され、例外が出ない。

- [ ] **Step 4: Commit**

```bash
git add products/d-manager/knowledge/__init__.py products/d-manager/config.py
git commit -m "feat(d-manager): knowledge engine の config と空パッケージを追加"
```

---

## Task 2: `knowledge/store.py` — digests テーブル

**Files:**
- Create: `products/d-manager/knowledge/store.py`
- Test: `products/d-manager/tests/test_knowledge_store.py`

- [ ] **Step 1: 失敗するテストを書く**

`products/d-manager/tests/test_knowledge_store.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge import store


@pytest.fixture
def db(tmp_path: Path):
    path = tmp_path / "knowledge.db"
    store.init_db(path)
    return path


def test_upsert_and_get(db):
    store.upsert_digest(
        db,
        channel_id="chan-1",
        channel_name="運営-jack-operations",
        department="operations",
        date="2026-05-12",
        source_kind="chat",
        turn_count=6,
        summary_md="## 議事録\n- メルカリ仕入れの重複チェック方針を決定",
        topics=["メルカリ仕入れ", "重複チェック"],
        decisions=[{"text": "差分チェックを9時バッチに入れる", "by": "jack"}],
        open_items=["駿河屋の在庫APIレート制限の確認"],
        next_actions=[{"text": "cron に追加", "owner": "Hiro"}],
        facts=["駿河屋APIは1分10リクエスト上限"],
    )
    rows = store.get_digests(db, "2026-05-12")
    assert len(rows) == 1
    r = rows[0]
    assert r["channel_id"] == "chan-1"
    assert r["source_kind"] == "chat"
    assert r["turn_count"] == 6
    assert "メルカリ仕入れ" in r["summary_md"]
    assert json.loads(r["topics_json"]) == ["メルカリ仕入れ", "重複チェック"]
    assert json.loads(r["decisions_json"])[0]["by"] == "jack"


def test_upsert_is_idempotent_per_channel_date(db):
    common = dict(
        db_path=db, channel_id="chan-1", channel_name="c", department="d",
        date="2026-05-12", source_kind="chat", turn_count=4,
        topics=None, decisions=None, open_items=None, next_actions=None, facts=None,
    )
    store.upsert_digest(summary_md="旧", **common)
    store.upsert_digest(summary_md="新", **common)
    rows = store.get_digests(db, "2026-05-12")
    assert len(rows) == 1
    assert rows[0]["summary_md"] == "新"


def test_search_finds_by_substring(db):
    store.upsert_digest(
        db, channel_id="c1", channel_name="c", department="d", date="2026-05-12",
        source_kind="chat", turn_count=5,
        summary_md="ファクセルのnote公開フローを確認した",
        topics=["note公開"], decisions=None, open_items=None, next_actions=None, facts=None,
    )
    hits = store.search(db, "note公開")
    assert any("note公開" in h["summary_md"] or "note公開" in (h["topics_json"] or "") for h in hits)


def test_get_digests_empty_day_returns_empty_list(db):
    assert store.get_digests(db, "2099-01-01") == []
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd products/d-manager && python -m pytest tests/test_knowledge_store.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'knowledge.store'` または同等）

- [ ] **Step 3: `knowledge/store.py` を実装**

`learning/store.py` の `_connect` / FTS5(trigram) パターンを踏襲する。

```python
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
                channel_id, channel_name, department, date, source_kind, turn_count,
                summary_md, _dump(topics), _dump(decisions), _dump(open_items),
                _dump(next_actions), _dump(facts), _now_iso(now),
            ),
        )
        # FTS は content='' の外部コンテンツ無しなので、行ごとに delete→insert で更新する
        try:
            conn.execute("DELETE FROM digests_fts WHERE rowid = (SELECT id FROM digests WHERE channel_id=? AND date=?)", (channel_id, date))
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


def get_digests(db_path: Path, date: str) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM digests WHERE date=? ORDER BY department, channel_name", (date,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def search(db_path: Path, query: str, limit: int = 50) -> list[dict]:
    conn = _connect(db_path)
    try:
        try:
            rows = conn.execute(
                "SELECT d.* FROM digests_fts f JOIN digests d ON d.id=f.rowid "
                "WHERE digests_fts MATCH ? ORDER BY d.date DESC LIMIT ?",
                (query, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            like = f"%{query.replace('%', '').replace('_', '')}%"
            rows = conn.execute(
                "SELECT * FROM digests WHERE summary_md LIKE ? OR COALESCE(topics_json,'') LIKE ? "
                "ORDER BY date DESC LIMIT ?",
                (like, like, limit),
            ).fetchall()
            return [dict(r) for r in rows]
    finally:
        conn.close()
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cd products/d-manager && python -m pytest tests/test_knowledge_store.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add products/d-manager/knowledge/store.py products/d-manager/tests/test_knowledge_store.py
git commit -m "feat(d-manager): knowledge/store.py — digests テーブル + FTS5"
```

---

## Task 3: `learning/store.py` に `list_sessions_for_date` を追加

**Files:**
- Modify: `products/d-manager/learning/store.py`（`list_pending_reviews` の直後に追加）
- Test: `products/d-manager/tests/test_learning_store.py`（末尾に追記）

- [ ] **Step 1: 失敗するテストを書く（`tests/test_learning_store.py` の末尾に追記）**

```python
def test_list_sessions_for_date(db):
    # 2026-05-10 に 3ターンのセッション、2026-05-11 に 1ターンのセッション
    for i in range(3):
        _record(db, channel_id="c10", role="user", content=f"q{i}",
                 now=dt.datetime(2026, 5, 10, 9, i, 0))
    _record(db, channel_id="c11", role="user", content="x",
            now=dt.datetime(2026, 5, 11, 9, 0, 0))

    got_all = store.list_sessions_for_date(db, "2026-05-10", min_turns=1)
    assert [s["channel_id"] for s in got_all] == ["c10"]
    assert got_all[0]["turn_count"] == 3

    # min_turns で絞れる
    assert store.list_sessions_for_date(db, "2026-05-11", min_turns=2) == []
    assert len(store.list_sessions_for_date(db, "2026-05-11", min_turns=1)) == 1

    # 該当日が無ければ空
    assert store.list_sessions_for_date(db, "2099-01-01", min_turns=1) == []
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd products/d-manager && python -m pytest tests/test_learning_store.py::test_list_sessions_for_date -v`
Expected: FAIL（`AttributeError: module 'learning.store' has no attribute 'list_sessions_for_date'`）

- [ ] **Step 3: `learning/store.py` に関数を追加（`list_pending_reviews` の直後）**

```python
def list_sessions_for_date(
    db_path: Path, date: str, min_turns: int = 1
) -> list[dict]:
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
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cd products/d-manager && python -m pytest tests/test_learning_store.py -v`
Expected: 既存テスト + 新規 1件すべて passed

- [ ] **Step 5: Commit**

```bash
git add products/d-manager/learning/store.py products/d-manager/tests/test_learning_store.py
git commit -m "feat(d-manager): learning/store に list_sessions_for_date を追加"
```

---

## Task 4: `knowledge/views.py` — digest を Markdown 書き出し

**Files:**
- Create: `products/d-manager/knowledge/views.py`
- Test: `products/d-manager/tests/test_knowledge_views.py`

- [ ] **Step 1: 失敗するテストを書く**

`products/d-manager/tests/test_knowledge_views.py`:

```python
from __future__ import annotations

from pathlib import Path

from knowledge import views


def test_write_digest_md_creates_file(tmp_path: Path):
    view_dir = tmp_path / "knowledge"
    p = views.write_digest_md(
        view_dir=view_dir,
        channel_name="運営-jack-operations",
        department="operations",
        date="2026-05-12",
        source_kind="chat",
        summary_md="## 議事録\n- メルカリ仕入れの方針決定",
        topics=["メルカリ仕入れ"],
        decisions=[{"text": "差分チェックを追加", "by": "jack"}],
        open_items=["駿河屋API確認"],
        next_actions=[{"text": "cron 追加", "owner": "Hiro"}],
        facts=["駿河屋APIは1分10req"],
    )
    assert p.exists()
    assert p.parent == view_dir / "digests"
    text = p.read_text(encoding="utf-8")
    assert "メルカリ仕入れの方針決定" in text
    assert "差分チェックを追加" in text
    assert "駿河屋API確認" in text
    # ファイル名は YYYY-MM-DD-<dept>-<channel safe>.md
    assert p.name.startswith("2026-05-12-operations-")
    assert p.suffix == ".md"


def test_write_digest_md_handles_none_sections(tmp_path: Path):
    view_dir = tmp_path / "knowledge"
    p = views.write_digest_md(
        view_dir=view_dir, channel_name="x/y:z", department="research",
        date="2026-05-12", source_kind="council",
        summary_md="council 索引: /path/to/meeting.md",
        topics=None, decisions=None, open_items=None, next_actions=None, facts=None,
    )
    assert p.exists()
    # チャンネル名の / : は安全文字に置換される（パスにならない）
    assert "/" not in p.name and ":" not in p.name
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd products/d-manager && python -m pytest tests/test_knowledge_views.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'knowledge.views'`）

- [ ] **Step 3: `knowledge/views.py` を実装**

```python
"""knowledge.db の内容を .company/secretary/knowledge/ 配下に Markdown で書き出す（人が読む/Obsidian/grep 用）。

SQLite が正データ。ここで書く Markdown はビューなので、.company/.gitignore で secretary/knowledge/ は除外する。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

_UNSAFE = re.compile(r"[^0-9A-Za-z぀-ヿ一-鿿_-]+")


def _safe(s: str) -> str:
    return _UNSAFE.sub("-", (s or "").strip()).strip("-") or "channel"


def _bullets(items: Optional[list], key: Optional[str] = None, owner_key: Optional[str] = None) -> str:
    if not items:
        return "_（なし）_\n"
    out = []
    for it in items:
        if isinstance(it, dict):
            text = it.get(key or "text") or ""
            who = it.get(owner_key or "owner") or it.get("by") or ""
            out.append(f"- {text}" + (f" — {who}" if who else ""))
        else:
            out.append(f"- {it}")
    return "\n".join(out) + "\n"


def write_digest_md(
    *,
    view_dir: Path,
    channel_name: str,
    department: str,
    date: str,
    source_kind: str,
    summary_md: str,
    topics: Optional[list],
    decisions: Optional[list],
    open_items: Optional[list],
    next_actions: Optional[list],
    facts: Optional[list],
) -> Path:
    out_dir = Path(view_dir) / "digests"
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{date}-{_safe(department)}-{_safe(channel_name)}.md"
    path = out_dir / fname
    body = (
        f"---\n"
        f"date: {date}\n"
        f"department: {department}\n"
        f"channel: {channel_name}\n"
        f"source_kind: {source_kind}\n"
        f"---\n\n"
        f"# {channel_name} — {date}\n\n"
        f"{summary_md.strip()}\n\n"
        f"## トピック\n{_bullets(topics)}\n"
        f"## 決定事項\n{_bullets(decisions, key='text', owner_key='by')}\n"
        f"## 未決事項\n{_bullets(open_items)}\n"
        f"## 次アクション\n{_bullets(next_actions, key='text', owner_key='owner')}\n"
        f"## 出てきた数字・事実\n{_bullets(facts)}"
    )
    path.write_text(body, encoding="utf-8")
    return path
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cd products/d-manager && python -m pytest tests/test_knowledge_views.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add products/d-manager/knowledge/views.py products/d-manager/tests/test_knowledge_views.py
git commit -m "feat(d-manager): knowledge/views.py — digest の Markdown 書き出し"
```

---

## Task 5: `knowledge/digest.py` — 議事録化本体

**Files:**
- Create: `products/d-manager/knowledge/digest.py`
- Test: `products/d-manager/tests/test_knowledge_digest.py`

`digest.py` は `learning.cli_runner.run_claude` を呼ぶ。テストでは `monkeypatch` でこれを差し替える。`run_claude` は `CliResult(ok, stdout, stderr, returncode, timed_out)` を返す（`learning/cli_runner.py` 参照）。

出力フォーマット契約: `claude -p` の stdout は「Markdown本文」+ 末尾に ` ```json ... ``` ` のフェンスブロック1つ（キー: `topics`(list[str]) / `decisions`(list[{text,by}]) / `open_items`(list[str]) / `next_actions`(list[{text,owner}]) / `facts`(list[str])）。フェンスが無い/壊れている場合は全文を `summary_md` にして JSON 系は `None`。

- [ ] **Step 1: 失敗するテストを書く**

`products/d-manager/tests/test_knowledge_digest.py`:

```python
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from knowledge import digest, store as kstore
from learning import store as lstore
from learning.cli_runner import CliResult


@pytest.fixture
def dbs(tmp_path: Path):
    ldb = tmp_path / "conversations.db"
    kdb = tmp_path / "knowledge.db"
    lstore.init_db(ldb)
    kstore.init_db(kdb)
    return ldb, kdb, tmp_path / "view"


def _turn(ldb, channel_id, role, content, when, **over):
    base = dict(
        db_path=ldb, channel_id=channel_id, channel_name="運営-jack-operations",
        department="operations", cli_session_id="s", role=role, content=content,
        engine="cli", origin="chat", reviewable=True, now=when,
    )
    base.update(over)
    return lstore.record_turn(**base)


_FAKE_OUT = (
    "## 議事録\n- メルカリ仕入れの重複チェック方針を決めた\n\n"
    "```json\n"
    '{"topics": ["メルカリ仕入れ"], "decisions": [{"text": "差分チェックを9時バッチに", "by": "jack"}], '
    '"open_items": ["駿河屋APIレート確認"], "next_actions": [{"text": "cron追加", "owner": "Hiro"}], '
    '"facts": ["駿河屋APIは1分10req"]}\n'
    "```\n"
)


def _ok(out=_FAKE_OUT):
    return CliResult(ok=True, stdout=out, stderr="", returncode=0, timed_out=False)


def test_build_daily_digests_happy_path(dbs, monkeypatch):
    ldb, kdb, view = dbs
    day = dt.datetime(2026, 5, 12, 9, 0, 0)
    for i in range(6):
        _turn(ldb, "chan-A", "user" if i % 2 == 0 else "assistant", f"msg{i}", day.replace(minute=i))

    calls = []
    def fake_run(prompt, **kw):
        calls.append(prompt)
        return _ok()
    monkeypatch.setattr("knowledge.digest.run_claude", fake_run)

    res = digest.build_daily_digests(
        date="2026-05-12", learning_db=ldb, knowledge_db=kdb, view_dir=view,
        company_dir=view.parent, meetings_dir=view.parent / "no-meetings",
        model="claude-x", min_turns=4, notification_channel_ids=(),
        timeout_sec=30, max_sessions=20,
    )
    assert res.processed == 1
    assert res.failed == 0
    assert len(calls) == 1
    rows = kstore.get_digests(kdb, "2026-05-12")
    assert len(rows) == 1
    assert "メルカリ仕入れ" in rows[0]["summary_md"]
    assert json.loads(rows[0]["decisions_json"])[0]["by"] == "jack"
    # Markdown も出ている
    mds = list((view / "digests").glob("2026-05-12-*.md"))
    assert len(mds) == 1


def test_skips_short_sessions(dbs, monkeypatch):
    ldb, kdb, view = dbs
    day = dt.datetime(2026, 5, 12, 9, 0, 0)
    _turn(ldb, "chan-short", "user", "ちょっとだけ", day)
    _turn(ldb, "chan-short", "assistant", "はい", day.replace(minute=1))  # 2 turns < 4
    monkeypatch.setattr("knowledge.digest.run_claude", lambda *a, **k: _ok())
    res = digest.build_daily_digests(
        date="2026-05-12", learning_db=ldb, knowledge_db=kdb, view_dir=view,
        company_dir=view.parent, meetings_dir=view.parent / "nope",
        model="m", min_turns=4, notification_channel_ids=(), timeout_sec=30, max_sessions=20,
    )
    assert res.processed == 0
    assert kstore.get_digests(kdb, "2026-05-12") == []


def test_skips_notification_channels(dbs, monkeypatch):
    ldb, kdb, view = dbs
    day = dt.datetime(2026, 5, 12, 9, 0, 0)
    for i in range(6):
        _turn(ldb, "notif-1", "user", f"x{i}", day.replace(minute=i))
    monkeypatch.setattr("knowledge.digest.run_claude", lambda *a, **k: _ok())
    res = digest.build_daily_digests(
        date="2026-05-12", learning_db=ldb, knowledge_db=kdb, view_dir=view,
        company_dir=view.parent, meetings_dir=view.parent / "nope",
        model="m", min_turns=4, notification_channel_ids=("notif-1",),
        timeout_sec=30, max_sessions=20,
    )
    assert res.processed == 0


def test_skips_command_only_sessions(dbs, monkeypatch):
    ldb, kdb, view = dbs
    day = dt.datetime(2026, 5, 12, 9, 0, 0)
    for i in range(6):
        # ユーザー発言がすべて "!..." の短文 → コマンドのみセッション
        _turn(ldb, "cmd-1", "user" if i % 2 == 0 else "assistant",
              "!status" if i % 2 == 0 else "OK: 稼働中", day.replace(minute=i))
    monkeypatch.setattr("knowledge.digest.run_claude", lambda *a, **k: _ok())
    res = digest.build_daily_digests(
        date="2026-05-12", learning_db=ldb, knowledge_db=kdb, view_dir=view,
        company_dir=view.parent, meetings_dir=view.parent / "nope",
        model="m", min_turns=4, notification_channel_ids=(), timeout_sec=30, max_sessions=20,
    )
    assert res.processed == 0


def test_claude_failure_is_counted_and_skipped(dbs, monkeypatch):
    ldb, kdb, view = dbs
    day = dt.datetime(2026, 5, 12, 9, 0, 0)
    for i in range(6):
        _turn(ldb, "chan-A", "user" if i % 2 == 0 else "assistant", f"m{i}", day.replace(minute=i))
    for i in range(6):
        _turn(ldb, "chan-B", "user" if i % 2 == 0 else "assistant", f"n{i}", day.replace(minute=10 + i))

    def fake_run(prompt, **kw):
        # chan-A 用は成功、chan-B 用は失敗（プロンプトにチャンネル名は入るが判別困難なので呼び順で）
        fake_run.n += 1
        if fake_run.n == 1:
            return _ok()
        return CliResult(ok=False, stdout="", stderr="boom", returncode=1, timed_out=False)
    fake_run.n = 0
    monkeypatch.setattr("knowledge.digest.run_claude", fake_run)

    res = digest.build_daily_digests(
        date="2026-05-12", learning_db=ldb, knowledge_db=kdb, view_dir=view,
        company_dir=view.parent, meetings_dir=view.parent / "nope",
        model="m", min_turns=4, notification_channel_ids=(), timeout_sec=30, max_sessions=20,
    )
    assert res.processed == 1
    assert res.failed == 1
    assert len(kstore.get_digests(kdb, "2026-05-12")) == 1


def test_idempotent_rerun(dbs, monkeypatch):
    ldb, kdb, view = dbs
    day = dt.datetime(2026, 5, 12, 9, 0, 0)
    for i in range(6):
        _turn(ldb, "chan-A", "user" if i % 2 == 0 else "assistant", f"m{i}", day.replace(minute=i))
    monkeypatch.setattr("knowledge.digest.run_claude", lambda *a, **k: _ok())
    kw = dict(date="2026-05-12", learning_db=ldb, knowledge_db=kdb, view_dir=view,
              company_dir=view.parent, meetings_dir=view.parent / "nope", model="m",
              min_turns=4, notification_channel_ids=(), timeout_sec=30, max_sessions=20)
    digest.build_daily_digests(**kw)
    digest.build_daily_digests(**kw)
    assert len(kstore.get_digests(kdb, "2026-05-12")) == 1


def test_index_council_meetings(dbs):
    ldb, kdb, view = dbs
    meetings = view.parent / "meetings"
    meetings.mkdir(parents=True)
    (meetings / "2026-05-12_経営会議.md").write_text(
        "# 経営会議 2026-05-12\n\n## 議題\n- 新プロダクトの優先順位\n\n（以下略）", encoding="utf-8"
    )
    (meetings / "2026-05-11_別の会議.md").write_text("古い会議", encoding="utf-8")
    n = digest.index_council_meetings(date="2026-05-12", knowledge_db=kdb, meetings_dir=meetings)
    assert n == 1
    rows = [r for r in kstore.get_digests(kdb, "2026-05-12") if r["source_kind"] == "council"]
    assert len(rows) == 1
    assert "経営会議" in rows[0]["summary_md"]
    assert "2026-05-12_経営会議.md" in rows[0]["summary_md"]
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd products/d-manager && python -m pytest tests/test_knowledge_digest.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'knowledge.digest'`）

- [ ] **Step 3: `knowledge/digest.py` を実装**

```python
"""フェーズ1: チャット→議事録化。

learning/store.py の turns/sessions を読み、セッション（チャンネル×日付）ごとに claude -p で
構造化議事録を作って knowledge/store.py に保存し、knowledge/views.py で Markdown も書き出す。
council スレッドの .md（.company/meetings/）はインデックスのみ。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from learning import store as lstore
from learning.cli_runner import run_claude
from learning.reviewer import format_conversation_log
from knowledge import store as kstore, views

logger = logging.getLogger(__name__)

_PERSONA = (
    "あなたは TrustLink の議事録ライターです。AI社員のような人格は持ちません。"
    "1日分の1チャンネルの会話ログを読み、何が議論され何が決まったかを構造化して書き出す単機能エージェントです。"
    "ファイル操作・外部コマンド・API 呼び出しは一切しません。出力は指定フォーマットのテキストのみです。"
    "APIキー・パスワード・トークンなど秘密情報が会話に出てきても、要約・JSON のどこにも書かず `***` でマスクしてください。"
)

_JSON_FENCE_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def _build_prompt(conversation_log: str) -> str:
    return f"""以下は d-manager（AI組織Bot）の1チャンネルでの1日分の会話ログです。
これを「あとで読み返して資産になる議事録」に要約してください。雑談・挨拶・コマンド出力は落とし、意味のある中身だけ残します。

出力フォーマット（厳守）:
1) まず Markdown 本文を書く（見出し `## 議事録` から始め、要点を箇条書きで。長くても300字程度）。
2) 本文の後に、機械可読の JSON を ```json フェンスで1つだけ付ける。キーは:
   - "topics": string[]（話題のラベル）
   - "decisions": {{"text": string, "by": string}}[]（決まったこと・誰が）
   - "open_items": string[]（未決・宿題）
   - "next_actions": {{"text": string, "owner": string}}[]（次にやること・担当）
   - "facts": string[]（出てきた数字・固有名詞・確定事実のメモ）
   該当が無いキーは空配列 [] にする。

会話に意味のある中身がほとんど無ければ、本文は `## 議事録\\n（特筆事項なし）` だけにし、JSON は全キー空配列にしてください。

---
{conversation_log}
"""


def _parse_output(stdout: str) -> tuple[str, Optional[list], Optional[list], Optional[list], Optional[list], Optional[list]]:
    text = (stdout or "").strip()
    m = _JSON_FENCE_RE.search(text)
    if not m:
        return text or "## 議事録\n（出力なし）", None, None, None, None, None
    summary = text[: m.start()].strip() or "## 議事録\n（本文なし）"
    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return summary, None, None, None, None, None

    def _list(key):
        v = data.get(key)
        return v if isinstance(v, list) and v else None

    return (
        summary, _list("topics"), _list("decisions"), _list("open_items"),
        _list("next_actions"), _list("facts"),
    )


def _is_command_only(turns: list[dict]) -> bool:
    """ユーザー発言がすべて短い `!` コマンドだけなら True（中身のないオペレーション）。"""
    user_msgs = [t["content"].strip() for t in turns if t["role"] == "user"]
    if not user_msgs:
        return True
    return all(m.startswith("!") and len(m) < 40 for m in user_msgs)


@dataclass
class DigestRun:
    processed: int = 0
    failed: int = 0
    skipped: int = 0
    council_indexed: int = 0
    notes: list[str] = field(default_factory=list)


def index_council_meetings(*, date: str, knowledge_db: Path, meetings_dir: Path) -> int:
    """`.company/meetings/<date>_*.md` を knowledge.db に source_kind='council' で索引登録。返り値=件数。"""
    mdir = Path(meetings_dir)
    if not mdir.exists():
        return 0
    n = 0
    for f in sorted(mdir.glob(f"{date}_*.md")):
        try:
            head = f.read_text(encoding="utf-8")[:500].strip()
        except OSError:
            continue
        kstore.upsert_digest(
            knowledge_db,
            channel_id=f"council:{f.name}",
            channel_name=f.stem,
            department="strategy",
            date=date,
            source_kind="council",
            turn_count=0,
            summary_md=f"council 議事録（索引）: `{f}`\n\n{head}",
            topics=None, decisions=None, open_items=None, next_actions=None, facts=None,
        )
        n += 1
    return n


def build_daily_digests(
    *,
    date: str,
    learning_db: Path,
    knowledge_db: Path,
    view_dir: Path,
    company_dir: Path,
    meetings_dir: Path,
    model: str,
    min_turns: int,
    notification_channel_ids: tuple,
    timeout_sec: int,
    max_sessions: int,
) -> DigestRun:
    kstore.init_db(knowledge_db)
    run = DigestRun()
    sessions = lstore.list_sessions_for_date(learning_db, date, min_turns=min_turns)
    notif = set(notification_channel_ids)

    for sess in sessions[:max_sessions]:
        cid = sess["channel_id"]
        if cid in notif:
            run.skipped += 1
            continue
        turns = lstore.get_session_turns(learning_db, cid, date)
        if len(turns) < min_turns or _is_command_only(turns):
            run.skipped += 1
            continue
        cname = sess.get("channel_name") or cid
        dept = sess.get("department") or "secretary"
        conv = format_conversation_log(cname, dept, date, turns)
        try:
            res = run_claude(
                prompt=_build_prompt(conv),
                cwd=Path(company_dir),
                model=model,
                allowed_tools="",
                disallowed_tools="Bash Edit Write WebFetch",
                system_prompt_append=_PERSONA,
                max_turns=1,
                timeout_sec=timeout_sec,
            )
        except Exception:  # noqa: BLE001
            logger.exception("knowledge.digest: run_claude raised for %s/%s", cid, date)
            run.failed += 1
            continue
        if not res.ok or not (res.stdout or "").strip():
            logger.warning("knowledge.digest: claude -p failed for %s/%s (rc=%s)", cid, date, res.returncode)
            run.failed += 1
            continue
        summary, topics, decisions, open_items, next_actions, facts = _parse_output(res.stdout)
        kstore.upsert_digest(
            knowledge_db, channel_id=cid, channel_name=cname, department=dept,
            date=date, source_kind="chat", turn_count=len(turns), summary_md=summary,
            topics=topics, decisions=decisions, open_items=open_items,
            next_actions=next_actions, facts=facts,
        )
        try:
            views.write_digest_md(
                view_dir=Path(view_dir), channel_name=cname, department=dept, date=date,
                source_kind="chat", summary_md=summary, topics=topics, decisions=decisions,
                open_items=open_items, next_actions=next_actions, facts=facts,
            )
        except OSError:
            logger.exception("knowledge.digest: write_digest_md failed for %s/%s", cid, date)
            run.notes.append(f"{cname}: Markdown書き出し失敗（DBには保存済み）")
        run.processed += 1

    try:
        run.council_indexed = index_council_meetings(
            date=date, knowledge_db=knowledge_db, meetings_dir=meetings_dir
        )
    except Exception:  # noqa: BLE001
        logger.exception("knowledge.digest: index_council_meetings failed")
    return run
```

> 注: `disallowed_tools="Bash Edit Write WebFetch"` は `claude -p` がうっかりファイルを触らないための保険。`allowed_tools=""` で基本ツール無しのはずだが二重で塞ぐ。

- [ ] **Step 4: テストが通ることを確認**

Run: `cd products/d-manager && python -m pytest tests/test_knowledge_digest.py -v`
Expected: 7 passed

- [ ] **Step 5: モジュール全体のテストを流す（既存を壊していないか）**

Run: `cd products/d-manager && python -m pytest -q`
Expected: 既存 + 新規すべて passed

- [ ] **Step 6: Commit**

```bash
git add products/d-manager/knowledge/digest.py products/d-manager/tests/test_knowledge_digest.py
git commit -m "feat(d-manager): knowledge/digest.py — チャット→議事録化（claude -p）"
```

---

## Task 6: `scheduler.py` に夜間ジョブ `knowledge_digest` を登録

**Files:**
- Modify: `products/d-manager/scheduler.py`
  - 関数定義: `async def learning_review()` の直後あたり（`async def learning_curate()` の前）に `async def knowledge_digest()` を追加
  - ジョブ登録: `setup_scheduler`（`_scheduler.add_job(...)` が並んでいる箇所）の `learning_review` の `add_job` の直後に1件追加
  - イベントハンドラ: 既存の `if event.job_id in ("learning_review", "weekly_review") and _send_fn:` の行のタプルに `"knowledge_digest"` は**追加しない**（このジョブは自前で `_send_fn` を呼ぶため。`learning_review` と同じ作り）

- [ ] **Step 1: `async def knowledge_digest()` を追加（`learning_review` の直後）**

```python
async def knowledge_digest():
    """夜間バッチ: その日のチャンネルごとの会話を構造化議事録にする（フェーズ1）。"""
    if not config.KNOWLEDGE_DIGEST_ENABLED:
        logger.info("knowledge_digest: disabled (KNOWLEDGE_DIGEST_ENABLED=false), skip")
        return
    logger.info("Running knowledge_digest...")
    import datetime as _dt

    from knowledge import digest as kdigest

    today = _dt.date.today().strftime("%Y-%m-%d")
    loop = asyncio.get_event_loop()
    run = await loop.run_in_executor(
        None,
        lambda: kdigest.build_daily_digests(
            date=today,
            learning_db=config.LEARNING_DB_PATH,
            knowledge_db=config.KNOWLEDGE_DB_PATH,
            view_dir=config.KNOWLEDGE_VIEW_DIR,
            company_dir=config.COMPANY_DIR,
            meetings_dir=config.COMPANY_DIR / "meetings",
            model=config.REVIEW_MODEL_CLI,
            min_turns=config.KNOWLEDGE_MIN_DIGEST_TURNS,
            notification_channel_ids=config.KNOWLEDGE_NOTIFICATION_CHANNEL_IDS,
            timeout_sec=config.KNOWLEDGE_DIGEST_TIMEOUT_SEC,
            max_sessions=config.KNOWLEDGE_DIGEST_MAX_SESSIONS,
        ),
    )
    lines = [
        f"📋 **今夜の議事録化**（{today}）: {run.processed}件 / 失敗{run.failed}件 "
        f"/ スキップ{run.skipped}件 / council索引{run.council_indexed}件"
    ]
    for note in run.notes:
        lines.append(f"⚠️ {note}")
    if _send_fn:
        try:
            await _send_fn(config.KNOWLEDGE_NOTIFY_CHANNEL, "\n".join(lines))
        except Exception:  # noqa: BLE001
            logger.exception("knowledge_digest: notify failed")
    logger.info("knowledge_digest done: %s", lines[0])
```

> 注: `asyncio` は scheduler.py で既に import 済み（`learning_review` 等が `asyncio.get_event_loop()` を使っている）。新規 import 不要。

- [ ] **Step 2: ジョブ登録を追加（`learning_review` の `add_job` の直後）**

`setup_scheduler` 内、`_scheduler.add_job(learning_review, "cron", hour=config.LEARNING_REVIEW_HOUR, ...)` のブロックの**直後**に以下を追加:

```python
    _scheduler.add_job(
        knowledge_digest,
        "cron",
        hour=config.KNOWLEDGE_DIGEST_HOUR,
        minute=config.KNOWLEDGE_DIGEST_MINUTE,
        id="knowledge_digest",
        name="知見エンジン: 夜間議事録化",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
```

- [ ] **Step 3: import チェック（構文・参照エラーが無いか）**

Run: `cd products/d-manager && python -c "import scheduler; print('ok', any(True for _ in [scheduler.knowledge_digest]))"`
Expected: `ok True`（例外なし）

- [ ] **Step 4: 全テストを流す**

Run: `cd products/d-manager && python -m pytest -q`
Expected: すべて passed

- [ ] **Step 5: Commit**

```bash
git add products/d-manager/scheduler.py
git commit -m "feat(d-manager): scheduler に夜間ジョブ knowledge_digest を追加（23:30）"
```

---

## Task 7: `main.py` に `!digest [YYYY-MM-DD]` コマンド

**Files:**
- Modify: `products/d-manager/main.py`（既存の `if raw.startswith("!learning"):` ブロックの近くに `if raw.startswith("!digest"):` を追加。`raw` はユーザー入力文字列）

`!learning` の処理を実装テンプレートとして参照すること（`main.py:616` 付近）。Discord への返信方法（`await message.channel.send(...)` 等）はそのブロックに合わせる。以下は処理ロジックの実体。

- [ ] **Step 1: `!digest` コマンドを追加**

`if raw.startswith("!learning"):` ブロックと同じ階層に、以下を追加（既存の返信ヘルパ名は `!learning` ブロックに合わせて置き換える。ここでは仮に `await message.channel.send(...)` とする）:

```python
    if raw.startswith("!digest"):
        import datetime as _dt

        from knowledge import digest as kdigest, store as kstore

        parts = raw.split()
        if len(parts) >= 2:
            target = parts[1]
        else:
            target = _dt.date.today().strftime("%Y-%m-%d")

        if "--run" in parts:
            run = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: kdigest.build_daily_digests(
                    date=target,
                    learning_db=config.LEARNING_DB_PATH,
                    knowledge_db=config.KNOWLEDGE_DB_PATH,
                    view_dir=config.KNOWLEDGE_VIEW_DIR,
                    company_dir=config.COMPANY_DIR,
                    meetings_dir=config.COMPANY_DIR / "meetings",
                    model=config.REVIEW_MODEL_CLI,
                    min_turns=config.KNOWLEDGE_MIN_DIGEST_TURNS,
                    notification_channel_ids=config.KNOWLEDGE_NOTIFICATION_CHANNEL_IDS,
                    timeout_sec=config.KNOWLEDGE_DIGEST_TIMEOUT_SEC,
                    max_sessions=config.KNOWLEDGE_DIGEST_MAX_SESSIONS,
                ),
            )
            await message.channel.send(
                f"📋 議事録化 {target}: 処理{run.processed} / 失敗{run.failed} / "
                f"スキップ{run.skipped} / council索引{run.council_indexed}"
            )
            return

        rows = await asyncio.get_event_loop().run_in_executor(
            None, kstore.get_digests, config.KNOWLEDGE_DB_PATH, target
        )
        if not rows:
            await message.channel.send(f"📋 {target} のダイジェストはまだありません（`!digest {target} --run` で生成）")
            return
        out = [f"📋 **{target} のダイジェスト** ({len(rows)}件)"]
        for r in rows:
            head = (r["summary_md"] or "").splitlines()
            first = next((ln for ln in head if ln.strip() and not ln.startswith("#")), "")
            out.append(f"・**{r['channel_name']}** ({r['source_kind']}): {first[:120]}")
        await message.channel.send("\n".join(out)[:1900])
        return
```

> 注: `asyncio` / `config` は main.py で既に import 済み（`!learning` ブロック等が使っている）。使われていなければ `import asyncio` を追加。`message` / `raw` の正確な変数名は周辺コードに合わせる。

- [ ] **Step 2: import チェック**

Run: `cd products/d-manager && python -c "import main; print('ok')"`
Expected: `ok`（例外なし）

- [ ] **Step 3: 全テストを流す**

Run: `cd products/d-manager && python -m pytest -q`
Expected: すべて passed

- [ ] **Step 4: Commit**

```bash
git add products/d-manager/main.py
git commit -m "feat(d-manager): !digest コマンド（一覧表示 / --run で手動生成）"
```

---

## Task 8: 朝ブリーフィングに前日ダイジェストの1行サマリ

**Files:**
- Modify: `products/d-manager/scheduler.py`（`async def morning_briefing():` の本文。`_send_fn` で送る最終メッセージ or プロンプト結果に1行足す）

`morning_briefing` は `process_message(...)` で本文を作って `_send_fn` で送っている（`scheduler.py:1129` 付近）。その送信直前に、前日の digest 件数＋主要トピックを1行で付け足す。

- [ ] **Step 1: `morning_briefing` に前日ダイジェスト行を追加**

`morning_briefing()` の中、`result`（briefing 本文）が組み上がり `_send_fn` に渡す直前に以下を挿入。`result` 変数名・送信箇所は周辺コードに合わせる:

```python
    # 前日のダイジェストサマリ（知見エンジン フェーズ1）
    try:
        import datetime as _dt

        from knowledge import store as kstore

        yday = (_dt.date.today() - _dt.timedelta(days=1)).strftime("%Y-%m-%d")
        drows = kstore.get_digests(config.KNOWLEDGE_DB_PATH, yday)
        if drows:
            topics = []
            for r in drows:
                if r["topics_json"]:
                    import json as _json

                    topics.extend(_json.loads(r["topics_json"]))
            uniq = list(dict.fromkeys(topics))[:5]
            line = f"\n\n📋 昨日のダイジェスト {len(drows)}件"
            if uniq:
                line += "｜主なトピック: " + " / ".join(uniq)
            result = (result or "") + line
    except Exception:  # noqa: BLE001
        logger.exception("morning_briefing: digest summary failed")
```

- [ ] **Step 2: import チェック**

Run: `cd products/d-manager && python -c "import scheduler; print('ok')"`
Expected: `ok`

- [ ] **Step 3: 全テストを流す**

Run: `cd products/d-manager && python -m pytest -q`
Expected: すべて passed

- [ ] **Step 4: Commit**

```bash
git add products/d-manager/scheduler.py
git commit -m "feat(d-manager): 朝ブリーフィングに前日ダイジェストの1行サマリ"
```

---

## Task 9: `.company/.gitignore` でMarkdownビューを除外

**Files:**
- Create / Modify: `/Users/Mac_air/Claude-Workspace/.company/.gitignore`

> `.company/`（= ワークスペース直下 `/Users/Mac_air/Claude-Workspace/.company`）は d-manager 本体とは別の git リポ（`.company/.git`）。`secretary/memory/` 等は引き続きコミット対象。`secretary/knowledge/`（digest/signals/stories の Markdownビュー）だけ除外する＝SQLite `knowledge.db` が正で Markdown は再生成可能なため、履歴肥大を避ける。

- [ ] **Step 1: `.gitignore` を作成（無ければ新規／あれば追記）**

`/Users/Mac_air/Claude-Workspace/.company/.gitignore` に1行追加:

```gitignore
secretary/knowledge/
```

- [ ] **Step 2: `.company` リポ側で反映確認**

Run: `cd /Users/Mac_air/Claude-Workspace/.company && git status --porcelain | grep -E 'secretary/knowledge|\.gitignore' || echo "(.gitignore のみ・knowledge/ は未追跡で無視される)"`
Expected: `.gitignore` が新規ファイルとして見える（`secretary/knowledge/` 配下は出てこない）。

- [ ] **Step 3: `.company` リポにコミット**

```bash
cd /Users/Mac_air/Claude-Workspace/.company && git add .gitignore && git commit -m "chore: secretary/knowledge/ を ignore（knowledge engine の Markdownビュー）"
```

> 注: `.company`（`/Users/Mac_air/Claude-Workspace/.company`）はワークスペース本体リポ（`/Users/Mac_air/Claude-Workspace`）とは別の独立 git リポ（サブモジュールではない）なので、コミットも別。ワークスペース本体側の `git status` には `.company/` の中身は出ない。本体側でこのプランの他タスクをコミットするときに `.company/` が巻き込まれないことを確認すること。

---

## Task 10: スモーク確認（手動・任意の1日で実行）

**Files:** （変更なし。動作確認のみ）

- [ ] **Step 1: 直近で会話のある日付を1つ選び、ドライ的に手動生成してみる**

`KNOWLEDGE_DIGEST_ENABLED` はまだ false のままでよい（`build_daily_digests` を直接呼ぶスモークなのでフラグは無関係）。実 `claude` CLI を1回だけ叩く:

Run:
```bash
cd /Users/Mac_air/Claude-Workspace/products/d-manager && python -c "
import config
from knowledge import digest
import learning.store as ls, datetime as dt
# 直近7日でセッションがある日を探す
for i in range(1, 8):
    d = (dt.date.today() - dt.timedelta(days=i)).strftime('%Y-%m-%d')
    if ls.list_sessions_for_date(config.LEARNING_DB_PATH, d, min_turns=config.KNOWLEDGE_MIN_DIGEST_TURNS):
        print('target day:', d)
        run = digest.build_daily_digests(
            date=d, learning_db=config.LEARNING_DB_PATH, knowledge_db=config.KNOWLEDGE_DB_PATH,
            view_dir=config.KNOWLEDGE_VIEW_DIR, company_dir=config.COMPANY_DIR,
            meetings_dir=config.COMPANY_DIR/'meetings', model=config.REVIEW_MODEL_CLI,
            min_turns=config.KNOWLEDGE_MIN_DIGEST_TURNS, notification_channel_ids=config.KNOWLEDGE_NOTIFICATION_CHANNEL_IDS,
            timeout_sec=config.KNOWLEDGE_DIGEST_TIMEOUT_SEC, max_sessions=3)
        print('result:', run)
        break
else:
    print('直近7日でセッションが見つからない（会話ログが空）。スキップ。')
"
```
Expected: `target day: 2026-05-..` と `result: DigestRun(processed=..., failed=..., ...)` が出る。`processed >= 1` が望ましい（会話があれば）。`claude` CLI 未インストール等なら `failed` がカウントされるが例外は出ない。

- [ ] **Step 2: 生成物を確認**

Run:
```bash
cd /Users/Mac_air/Claude-Workspace/products/d-manager && python -c "
import config
from knowledge import store
import datetime as dt
for i in range(1,8):
    d=(dt.date.today()-dt.timedelta(days=i)).strftime('%Y-%m-%d')
    rows=store.get_digests(config.KNOWLEDGE_DB_PATH, d)
    if rows:
        print(d, len(rows), 'digests')
        print(rows[0]['summary_md'][:200])
        break
"
ls -la /Users/Mac_air/Claude-Workspace/.company/secretary/knowledge/digests/ 2>/dev/null | head
```
Expected: digest 行が表示され、`.company/secretary/knowledge/digests/` に `.md` が1つ以上できている。

- [ ] **Step 3: 結果を要約して報告**

スモークの出力（target day / DigestRun / 生成された Markdown のファイル名と冒頭）を貼って完了報告する。`claude` CLI 起因の失敗があればその旨も明記する（黙って完了にしない — CLAUDE.md の自己検証ルール）。

- [ ] **Step 4: （Hiro の判断で）本番有効化**

問題なければ d-manager の起動環境（launchd）の環境変数 or `.env` に `KNOWLEDGE_DIGEST_ENABLED=true` を入れて再起動。これは Hiro に確認してから（不可逆ではないが本番挙動の変更）。このプランのタスクとしては「有効化を提案する」までで、自動では行わない。

---

## 完了の定義

- `knowledge/` モジュール（`store.py` / `digest.py` / `views.py`）+ `learning/store.list_sessions_for_date` + config + `scheduler.knowledge_digest` ジョブ + `!digest` コマンド + 朝ブリーフィング1行 + `.company/.gitignore` がすべて入っている。
- `cd products/d-manager && python -m pytest -q` が全 passed。
- スモーク（Task 10）で実 `claude` を1回叩いて digest が生成され、SQLite と `.company/secretary/knowledge/digests/` の両方に出ることを確認済み。
- `KNOWLEDGE_DIGEST_ENABLED` はデフォルト false のまま（本番有効化は Hiro の判断）。

## 後続（このプラン対象外）

- フェーズ2: シグナルDB + 抽出アダプタ（`knowledge/extractor.py` / `knowledge/sources/*`）— 別プラン
- フェーズ3: ストーリーDB（`knowledge/storyteller.py`）— 別プラン
- フェーズ4: コンサルmode + アラート（`knowledge/alerter.py` / `!ask-ceo`）— 別プラン
- フェーズ5: eBay リアルタイム戦略 — eBay 側プロダクト配下で別スペック・別プラン
