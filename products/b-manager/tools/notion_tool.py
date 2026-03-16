"""Notion integration — read/update tasks from Notion databases."""

import json
import logging
import os
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def get_notion_tasks(status_filter: str = "") -> Dict:
    """Get tasks from Notion database.

    Args:
        status_filter: Filter by status (e.g., "未着手", "進行中", "完了")
    """
    if not NOTION_API_KEY or not NOTION_DATABASE_ID:
        return {"error": "Notion APIキーまたはデータベースIDが設定されていません。"}

    body = {"page_size": 20}
    if status_filter:
        body["filter"] = {
            "property": "Status",
            "status": {"equals": status_filter},
        }

    try:
        resp = httpx.post(
            f"{NOTION_API}/databases/{NOTION_DATABASE_ID}/query",
            headers=_headers(),
            json=body,
            timeout=10,
        )
        if resp.status_code != 200:
            return {"error": f"Notion API error: {resp.status_code} {resp.text[:200]}"}

        data = resp.json()
        tasks = []
        for page in data.get("results", []):
            props = page.get("properties", {})
            title_prop = props.get("Name", props.get("タイトル", {}))
            title = ""
            if title_prop.get("title"):
                title = title_prop["title"][0]["plain_text"] if title_prop["title"] else ""

            status_prop = props.get("Status", props.get("ステータス", {}))
            status = ""
            if status_prop.get("status"):
                status = status_prop["status"].get("name", "")

            tasks.append({
                "id": page["id"],
                "title": title,
                "status": status,
                "url": page.get("url", ""),
            })

        return {"tasks": tasks, "count": len(tasks)}

    except Exception as e:
        return {"error": str(e)}


def update_notion_task(page_id: str, status: str) -> Dict:
    """Update a Notion task's status."""
    if not NOTION_API_KEY:
        return {"error": "Notion APIキーが設定されていません。"}

    try:
        resp = httpx.patch(
            f"{NOTION_API}/pages/{page_id}",
            headers=_headers(),
            json={
                "properties": {
                    "Status": {"status": {"name": status}},
                }
            },
            timeout=10,
        )
        if resp.status_code == 200:
            return {"status": "updated", "new_status": status}
        return {"error": f"Notion API error: {resp.status_code}"}

    except Exception as e:
        return {"error": str(e)}


def add_notion_task(title: str, status: str = "未着手") -> Dict:
    """Add a new task to Notion database."""
    if not NOTION_API_KEY or not NOTION_DATABASE_ID:
        return {"error": "Notion APIキーまたはデータベースIDが設定されていません。"}

    try:
        resp = httpx.post(
            f"{NOTION_API}/pages",
            headers=_headers(),
            json={
                "parent": {"database_id": NOTION_DATABASE_ID},
                "properties": {
                    "Name": {"title": [{"text": {"content": title}}]},
                    "Status": {"status": {"name": status}},
                },
            },
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {"id": data["id"], "title": title, "url": data.get("url", "")}
        return {"error": f"Notion API error: {resp.status_code} {resp.text[:200]}"}

    except Exception as e:
        return {"error": str(e)}
