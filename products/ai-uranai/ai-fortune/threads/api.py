"""Threads API クライアント"""

import asyncio
import logging
import os

import httpx

from database.crud import AsyncSessionLocal, get_setting, set_setting

logger = logging.getLogger(__name__)

THREADS_API_BASE = "https://graph.threads.net/v1.0"


async def _get_threads_token() -> str:
    """DBから長期トークンを取得。なければ環境変数にフォールバック"""
    async with AsyncSessionLocal() as session:
        token = await get_setting(session, "threads_access_token")
    if token:
        return token
    return os.environ.get("THREADS_ACCESS_TOKEN", "")


class ThreadsClient:
    def __init__(self, access_token: str = "", user_id: str = "") -> None:
        self._token = access_token
        self.user_id = user_id or os.environ.get("THREADS_USER_ID", "")

    async def _ensure_token(self) -> str:
        if not self._token:
            self._token = await _get_threads_token()
        return self._token

    async def get_my_username(self) -> str:
        """自分のThreadsユーザー名を取得する"""
        token = await self._ensure_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{THREADS_API_BASE}/{self.user_id}",
                params={
                    "fields": "username",
                    "access_token": token,
                },
            )
            resp.raise_for_status()
            return resp.json().get("username", "")

    async def create_text_post(self, text: str) -> str:
        """テキスト投稿を作成して投稿IDを返す"""
        token = await self._ensure_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{THREADS_API_BASE}/{self.user_id}/threads",
                params={
                    "media_type": "TEXT",
                    "text": text,
                    "access_token": token,
                },
            )
            resp.raise_for_status()
            container_id: str = resp.json()["id"]

            await asyncio.sleep(3)

            resp2 = await client.post(
                f"{THREADS_API_BASE}/{self.user_id}/threads_publish",
                params={
                    "creation_id": container_id,
                    "access_token": token,
                },
            )
            resp2.raise_for_status()
            return resp2.json()["id"]

    async def get_replies(self, post_id: str) -> list[dict]:
        """投稿への返信一覧を取得する"""
        token = await self._ensure_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{THREADS_API_BASE}/{post_id}/replies",
                params={
                    "fields": "id,text,username,timestamp",
                    "access_token": token,
                },
            )
            resp.raise_for_status()
            return resp.json().get("data", [])

    async def get_conversation(self, post_id: str) -> list[dict]:
        """投稿のコンバセーション（全返信ツリー）を取得する"""
        token = await self._ensure_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{THREADS_API_BASE}/{post_id}/conversation",
                params={
                    "fields": "id,text,username,timestamp",
                    "access_token": token,
                },
            )
            resp.raise_for_status()
            return resp.json().get("data", [])

    async def reply_to_thread(self, reply_to_id: str, text: str) -> str:
        """特定の投稿/コメントに返信する"""
        token = await self._ensure_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{THREADS_API_BASE}/{self.user_id}/threads",
                params={
                    "media_type": "TEXT",
                    "text": text,
                    "reply_to_id": reply_to_id,
                    "access_token": token,
                },
            )
            resp.raise_for_status()
            container_id: str = resp.json()["id"]

            await asyncio.sleep(3)

            resp2 = await client.post(
                f"{THREADS_API_BASE}/{self.user_id}/threads_publish",
                params={
                    "creation_id": container_id,
                    "access_token": token,
                },
            )
            resp2.raise_for_status()
            return resp2.json()["id"]

    async def get_post_insights(self, post_id: str) -> dict:
        """投稿のエンゲージメント指標を取得する"""
        token = await self._ensure_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{THREADS_API_BASE}/{post_id}/insights",
                params={
                    "metric": "likes,replies,reposts,quotes,views",
                    "access_token": token,
                },
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            metrics: dict = {}
            for item in data:
                name = item.get("name", "")
                values = item.get("values", [{}])
                metrics[name] = values[0].get("value", 0) if values else 0
            return metrics

    async def refresh_long_lived_token(self) -> str:
        """長期トークンをリフレッシュしてDBに保存する"""
        token = await self._ensure_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{THREADS_API_BASE}/refresh_access_token",
                params={
                    "grant_type": "th_refresh_token",
                    "access_token": token,
                },
            )
            resp.raise_for_status()
            new_token: str = resp.json()["access_token"]

        async with AsyncSessionLocal() as session:
            await set_setting(session, "threads_access_token", new_token)

        self._token = new_token
        logger.info("Threadsトークンをリフレッシュしました")
        return new_token
