"""Notion連携 — 投稿履歴をNotionコンテンツカレンダーDBに同期."""

import json
import logging
import urllib.request
from datetime import datetime

import config

logger = logging.getLogger(__name__)

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _notion_request(method: str, path: str, body: dict | None = None) -> dict | None:
    """Make a request to the Notion API."""
    if not config.NOTION_API_KEY or not config.NOTION_CALENDAR_DB_ID:
        return None

    url = f"{NOTION_API_URL}/{path}"
    headers = {
        "Authorization": f"Bearer {config.NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        logger.error(f"Notion API error ({method} {path}): {e}")
        return None


def sync_posted(post: dict) -> str | None:
    """投稿完了後にNotionページを作成。返値はNotionページID。"""
    if not config.NOTION_API_KEY:
        return None

    text = post.get("text", "")[:100]  # Title max 100 chars
    status_map = {
        "posted": "投稿済",
        "error": "エラー",
        "dry_run": "dry_run",
    }
    status = status_map.get(post.get("status", ""), "投稿済")
    post_type = post.get("post_type", "normal")
    created_at = post.get("created_at", datetime.now().isoformat())

    properties = {
        "投稿テキスト": {"title": [{"text": {"content": text}}]},
        "ステータス": {"select": {"name": status}},
        "パターン": {"rich_text": [{"text": {"content": post.get("pattern_id", "")}}]},
        "テーマ": {"rich_text": [{"text": {"content": post.get("theme", "")}}]},
        "品質スコア": {"number": post.get("avg_score")},
        "post_id": {"rich_text": [{"text": {"content": post.get("post_id", "")}}]},
        "投稿日時": {"date": {"start": created_at[:19]}},
    }

    if post_type in ("normal", "comment_bait", "thread_tree", "affiliate"):
        properties["投稿タイプ"] = {"select": {"name": post_type}}

    body = {
        "parent": {"database_id": config.NOTION_CALENDAR_DB_ID},
        "properties": properties,
    }

    result = _notion_request("POST", "pages", body)
    if result and "id" in result:
        logger.info(f"Notion synced: {result['id']}")
        return result["id"]
    return None


def update_metrics(post_id: str, metrics: dict) -> bool:
    """メトリクス取得後にNotionページを更新。post_idでNotionページを検索して更新。"""
    if not config.NOTION_API_KEY:
        return False

    # post_idでNotionページを検索
    search_body = {
        "filter": {
            "property": "post_id",
            "rich_text": {"equals": post_id},
        },
    }
    result = _notion_request(
        "POST",
        f"databases/{config.NOTION_CALENDAR_DB_ID}/query",
        search_body,
    )

    if not result or not result.get("results"):
        logger.warning(f"Notion page not found for post_id: {post_id}")
        return False

    page_id = result["results"][0]["id"]

    # メトリクス更新
    update_body = {
        "properties": {
            "閲覧数": {"number": metrics.get("views", 0)},
            "いいね": {"number": metrics.get("likes", 0)},
            "リプライ": {"number": metrics.get("replies", 0)},
        }
    }

    update_result = _notion_request("PATCH", f"pages/{page_id}", update_body)
    if update_result:
        logger.info(f"Notion metrics updated: {page_id}")
        return True
    return False
