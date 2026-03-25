"""状態管理ユーティリティ — JSON読み書き + KILL SWITCH"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from config import KILL_SWITCH_FILE, STATE_DIR

logger = logging.getLogger(__name__)

# 初期化: stateディレクトリとデフォルトファイルを確保
STATE_DIR.mkdir(exist_ok=True)

_DEFAULT_FILES: dict[str, Any] = {
    "post_history.json": [],
    "post_queue.json": [],
    "research_cache.json": [],
    "analyst_feedback.json": {"updated_at": None, "directives": []},
}


def _ensure_state_file(name: str) -> Path:
    path = STATE_DIR / name
    if not path.exists():
        default = _DEFAULT_FILES.get(name, {})
        path.write_text(json.dumps(default, ensure_ascii=False, indent=2))
    return path


def load_state(name: str) -> Any:
    path = _ensure_state_file(name)
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(name: str, data: Any) -> None:
    path = STATE_DIR / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------------------------------------------
# 投稿履歴
# ------------------------------------------------------------------

def get_post_history(limit: int = 100) -> list[dict]:
    history = load_state("post_history.json")
    return history[-limit:]


def add_post_to_history(post: dict) -> None:
    history = load_state("post_history.json")
    post.setdefault("created_at", datetime.now().isoformat())
    history.append(post)
    save_state("post_history.json", history)

    # Notion同期（非ブロッキング、失敗しても継続）
    try:
        from notion_sync import sync_posted
        sync_posted(post)
    except Exception as e:
        logger.warning(f"Notion sync skipped: {e}")


def update_post_metrics(post_id: str, metrics: dict) -> None:
    history = load_state("post_history.json")
    for p in history:
        if p.get("post_id") == post_id:
            p["metrics"] = metrics
            p["metrics_fetched_at"] = datetime.now().isoformat()
            break
    save_state("post_history.json", history)

    # Notionメトリクス更新
    try:
        from notion_sync import update_metrics
        update_metrics(post_id, metrics)
    except Exception as e:
        logger.warning(f"Notion metrics sync skipped: {e}")


# ------------------------------------------------------------------
# 投稿キュー
# ------------------------------------------------------------------

def get_queue() -> list[dict]:
    return load_state("post_queue.json")


def add_to_queue(posts: list[dict]) -> None:
    queue = load_state("post_queue.json")
    queue.extend(posts)
    save_state("post_queue.json", queue)


def pop_from_queue() -> dict | None:
    queue = load_state("post_queue.json")
    if not queue:
        return None
    post = queue.pop(0)
    save_state("post_queue.json", queue)
    return post


# ------------------------------------------------------------------
# リサーチキャッシュ
# ------------------------------------------------------------------

def get_research_cache() -> list[dict]:
    return load_state("research_cache.json")


def add_research(items: list[dict]) -> None:
    cache = load_state("research_cache.json")
    cache.extend(items)
    # 最大500件に制限
    if len(cache) > 500:
        cache = cache[-500:]
    save_state("research_cache.json", cache)


# ------------------------------------------------------------------
# アナリストフィードバック
# ------------------------------------------------------------------

def get_analyst_feedback() -> dict:
    return load_state("analyst_feedback.json")


def save_analyst_feedback(feedback: dict) -> None:
    feedback["updated_at"] = datetime.now().isoformat()
    save_state("analyst_feedback.json", feedback)


# ------------------------------------------------------------------
# KILL SWITCH
# ------------------------------------------------------------------

def is_kill_switch_active() -> bool:
    return KILL_SWITCH_FILE.exists()


def activate_kill_switch(reason: str = "") -> None:
    KILL_SWITCH_FILE.write_text(
        json.dumps({"activated_at": datetime.now().isoformat(), "reason": reason}),
        encoding="utf-8",
    )
    logger.critical("KILL SWITCH 発動: %s", reason)


def deactivate_kill_switch() -> None:
    if KILL_SWITCH_FILE.exists():
        KILL_SWITCH_FILE.unlink()
        logger.info("KILL SWITCH 解除")
