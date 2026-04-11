"""Atlas Cloud Seedance 2.0 I2V API クライアント。
承認済み画像を10秒の9:16動画に変換する。
"""
from __future__ import annotations
import asyncio
import base64
import logging
from pathlib import Path
import httpx
from config import (
    ATLAS_CLOUD_API_KEY,
    ATLAS_CLOUD_I2V_URL,
    ATLAS_CLOUD_STATUS_URL,
    VIDEO_DURATION,
    VIDEO_ASPECT_RATIO,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
POLL_INTERVAL = 15.0
TIMEOUT_SECONDS = 300.0  # 5分


class VideoGenError(Exception):
    pass


async def generate_video(image_path: Path, video_prompt: str, output_path: Path) -> Path:
    """Seedance 2.0 I2V で動画を生成して output_path に保存する。"""
    image_b64 = base64.b64encode(image_path.read_bytes()).decode()
    headers = {
        "x-api-key": ATLAS_CLOUD_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": video_prompt,
        "images_list": [f"data:image/jpeg;base64,{image_b64}"],
        "aspect_ratio": VIDEO_ASPECT_RATIO,
        "duration": VIDEO_DURATION,
        "quality": "basic",
    }

    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # ジョブ投入
                resp = await client.post(ATLAS_CLOUD_I2V_URL, headers=headers, json=payload)
                if resp.status_code != 200:
                    last_error = VideoGenError(f"Submit failed HTTP {resp.status_code}: {resp.text[:200]}")
                    logger.warning(f"Attempt {attempt}: {last_error}")
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(10.0)
                    continue

                request_id = resp.json()["request_id"]
                logger.info(f"動画生成ジョブ投入: {request_id}")

                # ポーリング
                video_url = await _poll_until_done(client, request_id, headers)

                # ダウンロード
                dl_resp = await client.get(video_url, timeout=120.0)
                dl_resp.raise_for_status()
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(dl_resp.content)
                logger.info(f"動画保存完了: {output_path}")
                return output_path

            except (VideoGenError, httpx.RequestError) as e:
                last_error = e
                logger.warning(f"Attempt {attempt} failed: {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(10.0)

    raise VideoGenError(f"動画生成失敗（{MAX_RETRIES}回リトライ済み）: {last_error}")


async def _poll_until_done(
    client: httpx.AsyncClient, request_id: str, headers: dict
) -> str:
    """ステータスが 'done' になるまでポーリング。video URLを返す。"""
    status_url = ATLAS_CLOUD_STATUS_URL.format(request_id=request_id)
    elapsed = 0.0
    while elapsed < TIMEOUT_SECONDS:
        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        resp = await client.get(status_url, headers=headers)
        data = resp.json()
        status = data.get("status")
        if status == "done":
            return data["output_url"]
        if status == "failed":
            raise VideoGenError(f"Atlas Cloud でジョブ失敗: {data}")
        logger.info(f"ポーリング中 ({elapsed:.0f}s): {status}")
    raise VideoGenError(f"タイムアウト: {TIMEOUT_SECONDS}秒以内に完了しなかった")
