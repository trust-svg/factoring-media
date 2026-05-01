"""muapi.ai 経由 Kling V3.0 Pro I2V クライアント。"""

from __future__ import annotations
import asyncio
import logging
import os
from pathlib import Path
import httpx
from config import ATLAS_CLOUD_API_KEY, ATLAS_CLOUD_STATUS_URL
from core.video_providers import VideoProvider, VideoGenRequest
from core.video_providers._telegram_upload import upload_image_to_telegram
from core.camera_presets import get_kling_params, get_prompt_hint

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 10.0
POLL_INTERVAL = 15.0
TIMEOUT_SECONDS = 900.0
RATE_LIMIT_WAIT = 30.0
COST_PER_VIDEO_USD = 0.46  # 概算（muapi.ai 公称値）


class KlingError(Exception):
    pass


class Kling3ProProvider(VideoProvider):
    name = "kling3_pro"
    supported_aspects = ("9:16", "16:9", "1:1")
    supported_durations = (5, 10)

    def calc_cost(self, req: VideoGenRequest) -> float:
        return COST_PER_VIDEO_USD

    def _i2v_url(self) -> str:
        return os.environ.get(
            "MUAPI_KLING_I2V_URL",
            "https://api.muapi.ai/api/v1/kling-v3-pro-i2v",
        )

    def _build_payload(self, req: VideoGenRequest, image_url: str) -> dict:
        prompt = req.video_prompt
        hint = get_prompt_hint(req.camera_preset)
        if hint:
            prompt = f"{prompt}, {hint}"

        payload = {
            "prompt": prompt,
            "image": image_url,
            "aspect_ratio": req.aspect_ratio,
            "duration": req.duration_seconds,
        }

        kling_params = get_kling_params(req.camera_preset)
        if kling_params:
            payload["camera_control"] = {
                "type": "simple",
                "config": kling_params,
            }
        return payload

    async def generate(self, req: VideoGenRequest) -> Path:
        self.validate(req)
        image_url = await upload_image_to_telegram(req.image_path)
        payload = self._build_payload(req, image_url)
        headers = {"x-api-key": ATLAS_CLOUD_API_KEY, "Content-Type": "application/json"}

        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=60.0) as client:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    resp = await client.post(
                        self._i2v_url(), headers=headers, json=payload
                    )
                    if resp.status_code in (401, 402, 403):
                        raise KlingError(
                            f"auth/billing HTTP {resp.status_code}: {resp.text[:200]}"
                        )
                    if resp.status_code == 429:
                        await asyncio.sleep(RATE_LIMIT_WAIT)
                        last_error = KlingError(f"HTTP 429: {resp.text[:200]}")
                        continue
                    if 400 <= resp.status_code < 500:
                        raise KlingError(
                            f"client error HTTP {resp.status_code}: {resp.text[:200]}"
                        )
                    if resp.status_code >= 500:
                        last_error = KlingError(
                            f"server error HTTP {resp.status_code}: {resp.text[:200]}"
                        )
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(RETRY_DELAY)
                        continue

                    request_id = resp.json()["request_id"]
                    video_url = await self._poll(client, request_id, headers)
                    dl_resp = await client.get(video_url, timeout=120.0)
                    dl_resp.raise_for_status()
                    req.output_path.parent.mkdir(parents=True, exist_ok=True)
                    req.output_path.write_bytes(dl_resp.content)
                    return req.output_path
                except KlingError:
                    raise
                except httpx.RequestError as e:
                    last_error = e
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(RETRY_DELAY)

        raise KlingError(f"failed after {MAX_RETRIES} retries: {last_error}")

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
                raise KlingError(f"status URL 404: {status_url}")
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
                raise KlingError(f"completed without output URL: {data}")
            if status in ("failed", "error", "cancelled"):
                raise KlingError(f"job failed: {data}")
        raise KlingError(f"timeout {TIMEOUT_SECONDS}s")
