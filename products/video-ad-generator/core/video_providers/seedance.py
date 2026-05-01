"""Atlas Cloud Seedance 2.0 I2V API クライアント（VideoProvider 実装）。"""

from __future__ import annotations
import asyncio
import logging
from pathlib import Path
import httpx
from config import (
    ATLAS_CLOUD_API_KEY,
    ATLAS_CLOUD_I2V_URL,
    ATLAS_CLOUD_STATUS_URL,
)
from core.video_providers import VideoProvider, VideoGenRequest
from core.video_providers._telegram_upload import upload_image_to_telegram
from core.camera_presets import get_prompt_hint

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 10.0
POLL_INTERVAL = 15.0
TIMEOUT_SECONDS = 900.0
RATE_LIMIT_WAIT = 30.0


class SeedanceError(Exception):
    pass


class SeedanceProvider(VideoProvider):
    name = "seedance"
    supported_aspects = ("9:16", "16:9", "1:1", "4:3", "3:4", "21:9")
    supported_durations = (5, 10)
    cost_basis = "per_second"
    RATE_MAP = {"low": 0.081, "high": 0.13}
    QUALITY_MAP = {"low": "basic", "high": "pro"}

    def _build_prompt(self, req: VideoGenRequest) -> str:
        hint = get_prompt_hint(req.camera_preset)
        if hint:
            return f"{req.video_prompt}, {hint}"
        return req.video_prompt

    async def generate(self, req: VideoGenRequest) -> Path:
        self.validate(req)
        headers = {
            "x-api-key": ATLAS_CLOUD_API_KEY,
            "Content-Type": "application/json",
        }
        image_url = await upload_image_to_telegram(req.image_path)
        logger.info("[seedance] image uploaded to telegram")

        payload = {
            "prompt": self._build_prompt(req),
            "images_list": [image_url],
            "aspect_ratio": req.aspect_ratio,
            "duration": req.duration_seconds,
            "quality": self.QUALITY_MAP[req.quality],
        }

        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=60.0) as client:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    resp = await client.post(
                        ATLAS_CLOUD_I2V_URL, headers=headers, json=payload
                    )

                    # 認証/課金エラーは即時失敗
                    if resp.status_code in (401, 402, 403):
                        raise SeedanceError(
                            f"auth/billing error HTTP {resp.status_code}: {resp.text[:200]}"
                        )
                    # Rate limit
                    if resp.status_code == 429:
                        logger.warning(
                            f"[seedance] rate limited, waiting {RATE_LIMIT_WAIT}s"
                        )
                        await asyncio.sleep(RATE_LIMIT_WAIT)
                        last_error = SeedanceError(f"HTTP 429: {resp.text[:200]}")
                        continue
                    # その他 4xx は即時失敗
                    if 400 <= resp.status_code < 500:
                        raise SeedanceError(
                            f"client error HTTP {resp.status_code}: {resp.text[:200]}"
                        )
                    # 5xx はリトライ
                    if resp.status_code >= 500:
                        last_error = SeedanceError(
                            f"server error HTTP {resp.status_code}: {resp.text[:200]}"
                        )
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(RETRY_DELAY)
                        continue

                    resp_data = resp.json()
                    request_id = resp_data["request_id"]
                    logger.info(f"[seedance] submitted: {request_id}")

                    video_url = await self._poll(client, request_id, headers)

                    dl_resp = await client.get(video_url, timeout=120.0)
                    dl_resp.raise_for_status()
                    req.output_path.parent.mkdir(parents=True, exist_ok=True)
                    req.output_path.write_bytes(dl_resp.content)
                    return req.output_path

                except SeedanceError:
                    raise
                except httpx.RequestError as e:
                    last_error = e
                    logger.warning(f"[seedance] attempt {attempt} network error: {e}")
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(RETRY_DELAY)

        raise SeedanceError(f"failed after {MAX_RETRIES} retries: {last_error}")

    async def _poll(
        self, client: httpx.AsyncClient, request_id: str, headers: dict
    ) -> str:
        status_url = ATLAS_CLOUD_STATUS_URL.format(request_id=request_id)
        elapsed = 0.0
        while elapsed < TIMEOUT_SECONDS:
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
            resp = await client.get(status_url, headers=headers)
            if resp.status_code == 404:
                raise SeedanceError(f"status URL 404: {status_url}")
            data = resp.json()
            status = data.get("status")
            outputs = data.get("outputs") or []
            output_url = (
                outputs[0]
                if outputs
                else (data.get("output_url") or data.get("video_url"))
            )
            if status in ("done", "succeeded", "completed", "success"):
                if output_url:
                    return output_url
                raise SeedanceError(f"completed without output URL: {data}")
            if status in ("failed", "error", "cancelled"):
                raise SeedanceError(f"job failed: {data}")
        raise SeedanceError(f"timeout {TIMEOUT_SECONDS}s")
