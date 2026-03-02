"""Threads API クライアント"""

import asyncio
import os

import httpx

THREADS_API_BASE = "https://graph.threads.net/v1.0"


class ThreadsClient:
    def __init__(self) -> None:
        self.access_token = os.environ["THREADS_ACCESS_TOKEN"]
        self.user_id = os.environ["THREADS_USER_ID"]

    async def create_text_post(self, text: str) -> str:
        """テキスト投稿を作成して投稿IDを返す"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: メディアコンテナ作成
            resp = await client.post(
                f"{THREADS_API_BASE}/{self.user_id}/threads",
                params={
                    "media_type": "TEXT",
                    "text": text,
                    "access_token": self.access_token,
                },
            )
            resp.raise_for_status()
            container_id: str = resp.json()["id"]

            # Threads API はコンテナ作成後に数秒の待機が必要
            await asyncio.sleep(3)

            # Step 2: 投稿公開
            resp2 = await client.post(
                f"{THREADS_API_BASE}/{self.user_id}/threads_publish",
                params={
                    "creation_id": container_id,
                    "access_token": self.access_token,
                },
            )
            resp2.raise_for_status()
            return resp2.json()["id"]

    async def get_recent_posts(self, limit: int = 10) -> list[dict]:
        """最近の投稿一覧を取得"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{THREADS_API_BASE}/{self.user_id}/threads",
                params={
                    "fields": "id,text,timestamp",
                    "limit": limit,
                    "access_token": self.access_token,
                },
            )
            resp.raise_for_status()
            return resp.json().get("data", [])

    async def refresh_long_lived_token(self) -> str:
        """長期アクセストークンを更新する（60日ごとに実行）"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{THREADS_API_BASE}/refresh_access_token",
                params={
                    "grant_type": "th_refresh_token",
                    "access_token": self.access_token,
                },
            )
            resp.raise_for_status()
            new_token: str = resp.json()["access_token"]
            return new_token
