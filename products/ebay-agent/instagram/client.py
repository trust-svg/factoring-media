"""Meta Graph API クライアント — Instagram投稿・分析

Note: Meta APIトークン未取得のため、現時点ではモック実装。
トークン取得後に実APIに切り替え可能な設計。
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


class InstagramClient:
    """Meta Graph API 経由の Instagram 操作"""

    def __init__(self):
        self.access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
        self.ig_user_id = os.getenv("INSTAGRAM_USER_ID", "")
        self._mock_mode = not (self.access_token and self.ig_user_id)
        if self._mock_mode:
            logger.info("Instagram client: モックモード（API未接続）")

    @property
    def is_connected(self) -> bool:
        return not self._mock_mode

    def _api_call(self, method: str, endpoint: str, **kwargs) -> dict:
        """Graph API 呼び出し共通処理"""
        if self._mock_mode:
            return {"mock": True, "endpoint": endpoint}

        url = f"{GRAPH_API_BASE}/{endpoint}"
        kwargs.setdefault("params", {})
        kwargs["params"]["access_token"] = self.access_token

        resp = requests.request(method, url, timeout=30, **kwargs)
        resp.raise_for_status()
        return resp.json()

    # ── 投稿 ──────────────────────────────────────────────

    def create_media_container(
        self,
        image_url: str,
        caption: str,
        is_carousel_item: bool = False,
    ) -> str:
        """メディアコンテナ作成（Step 1）"""
        if self._mock_mode:
            import uuid
            mock_id = f"mock_container_{uuid.uuid4().hex[:8]}"
            logger.info(f"[MOCK] メディアコンテナ作成: {mock_id}")
            return mock_id

        params = {
            "image_url": image_url,
            "access_token": self.access_token,
        }
        if is_carousel_item:
            params["is_carousel_item"] = "true"
        else:
            params["caption"] = caption

        resp = requests.post(
            f"{GRAPH_API_BASE}/{self.ig_user_id}/media",
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def create_carousel_container(
        self,
        children_ids: list[str],
        caption: str,
    ) -> str:
        """カルーセルコンテナ作成"""
        if self._mock_mode:
            import uuid
            mock_id = f"mock_carousel_{uuid.uuid4().hex[:8]}"
            logger.info(f"[MOCK] カルーセルコンテナ作成: {mock_id} ({len(children_ids)}枚)")
            return mock_id

        params = {
            "media_type": "CAROUSEL",
            "children": ",".join(children_ids),
            "caption": caption,
            "access_token": self.access_token,
        }
        resp = requests.post(
            f"{GRAPH_API_BASE}/{self.ig_user_id}/media",
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def publish_media(self, container_id: str) -> str:
        """メディア公開（Step 2）"""
        if self._mock_mode:
            import uuid
            mock_id = f"mock_post_{uuid.uuid4().hex[:8]}"
            logger.info(f"[MOCK] 投稿公開: {mock_id}")
            return mock_id

        resp = requests.post(
            f"{GRAPH_API_BASE}/{self.ig_user_id}/media_publish",
            params={
                "creation_id": container_id,
                "access_token": self.access_token,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    # ── 分析 ──────────────────────────────────────────────

    def get_media_insights(self, media_id: str) -> dict:
        """投稿パフォーマンス取得"""
        if self._mock_mode:
            return {
                "impressions": 0,
                "reach": 0,
                "likes": 0,
                "comments": 0,
                "saved": 0,
            }

        resp = requests.get(
            f"{GRAPH_API_BASE}/{media_id}/insights",
            params={
                "metric": "impressions,reach,saved",
                "access_token": self.access_token,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        result = {}
        for metric in data:
            result[metric["name"]] = metric["values"][0]["value"]
        return result

    def get_account_insights(self, period: str = "day", days: int = 7) -> dict:
        """アカウントレベルのインサイト取得"""
        if self._mock_mode:
            return {
                "mock": True,
                "follower_count": 0,
                "impressions": 0,
                "reach": 0,
                "profile_views": 0,
            }

        resp = requests.get(
            f"{GRAPH_API_BASE}/{self.ig_user_id}/insights",
            params={
                "metric": "impressions,reach,profile_views,follower_count",
                "period": period,
                "access_token": self.access_token,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        result = {}
        for metric in data:
            values = metric.get("values", [])
            result[metric["name"]] = values[-1]["value"] if values else 0
        return result
