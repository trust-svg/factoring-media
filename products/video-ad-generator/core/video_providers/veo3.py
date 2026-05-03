"""Google Gemini API 経由 Veo 3.1 Lite I2V クライアント。"""

from __future__ import annotations
import asyncio
import logging
from pathlib import Path
import base64
import httpx
from core.video_providers import VideoProvider, VideoGenRequest
from core.camera_presets import get_prompt_hint

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 10.0
POLL_INTERVAL = 15.0
TIMEOUT_SECONDS = 900.0
RATE_LIMIT_WAIT = 30.0


class Veo3Error(Exception):
    pass


class Veo3LiteProvider(VideoProvider):
    name = "veo3_lite"
    supported_aspects = ("16:9", "9:16")
    # 参照画像必須 (i2v) のため Veo 3.1 仕様で 8 秒のみ許可
    supported_durations = (8,)
    cost_basis = "per_second"
    RATE_MAP = {"low": 0.10, "high": 0.40}
    MODEL_MAP = {
        "low": "veo-3.1-fast-generate-preview",
        "high": "veo-3.1-generate-preview",
    }

    def _build_prompt(self, req: VideoGenRequest) -> str:
        hint = get_prompt_hint(req.camera_preset)
        return f"{req.video_prompt}, {hint}" if hint else req.video_prompt

    def _api_key(self) -> str:
        from config import GEMINI_API_KEY

        return GEMINI_API_KEY

    def _model_id(self, req: VideoGenRequest) -> str:
        return self.MODEL_MAP[req.quality]

    def _generate_url(self, req: VideoGenRequest) -> str:
        return f"https://generativelanguage.googleapis.com/v1beta/models/{self._model_id(req)}:generateVideo"

    def _operation_url(self, op_name: str) -> str:
        return f"https://generativelanguage.googleapis.com/v1beta/{op_name}"

    async def generate(self, req: VideoGenRequest) -> Path:
        self.validate(req)
        image_b64 = base64.b64encode(req.image_path.read_bytes()).decode("ascii")
        suffix = req.image_path.suffix.lower()
        mime_type = "image/png" if suffix == ".png" else "image/jpeg"

        payload = {
            "instances": [
                {
                    "prompt": self._build_prompt(req),
                    "image": {
                        "bytesBase64Encoded": image_b64,
                        "mimeType": mime_type,
                    },
                }
            ],
            "parameters": {
                "aspectRatio": req.aspect_ratio,
                "durationSeconds": req.duration_seconds,
                "sampleCount": 1,
            },
        }
        params = {"key": self._api_key()}

        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=60.0) as client:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    resp = await client.post(
                        self._generate_url(req), params=params, json=payload
                    )
                    if resp.status_code in (401, 402, 403):
                        raise Veo3Error(
                            f"auth/billing HTTP {resp.status_code}: {resp.text[:200]}"
                        )
                    if resp.status_code == 429:
                        await asyncio.sleep(RATE_LIMIT_WAIT)
                        last_error = Veo3Error(f"HTTP 429: {resp.text[:200]}")
                        continue
                    if 400 <= resp.status_code < 500:
                        raise Veo3Error(
                            f"client error HTTP {resp.status_code}: {resp.text[:200]}"
                        )
                    if resp.status_code >= 500:
                        last_error = Veo3Error(
                            f"server error HTTP {resp.status_code}: {resp.text[:200]}"
                        )
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(RETRY_DELAY)
                        continue

                    op = resp.json()
                    op_name = op.get("name")
                    if not op_name:
                        raise Veo3Error(f"no operation name in response: {op}")

                    video_url = await self._poll(client, op_name, params)
                    dl_resp = await client.get(video_url, params=params, timeout=120.0)
                    dl_resp.raise_for_status()
                    req.output_path.parent.mkdir(parents=True, exist_ok=True)
                    req.output_path.write_bytes(dl_resp.content)
                    return req.output_path

                except Veo3Error:
                    raise
                except httpx.RequestError as e:
                    last_error = e
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(RETRY_DELAY)

        raise Veo3Error(f"failed after {MAX_RETRIES} retries: {last_error}")

    async def _poll(self, client: httpx.AsyncClient, op_name: str, params: dict) -> str:
        elapsed = 0.0
        while elapsed < TIMEOUT_SECONDS:
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
            resp = await client.get(self._operation_url(op_name), params=params)
            if resp.status_code != 200:
                raise Veo3Error(
                    f"poll error HTTP {resp.status_code}: {resp.text[:200]}"
                )
            data = resp.json()
            if data.get("done"):
                if "error" in data:
                    raise Veo3Error(f"operation failed: {data['error']}")
                response = data.get("response", {})
                videos = response.get("generatedVideos") or response.get("videos") or []
                if not videos:
                    raise Veo3Error(f"no video in response: {data}")
                video = videos[0]
                video_uri = video.get("video", {}).get("uri") or video.get("uri")
                if not video_uri:
                    raise Veo3Error(f"no video URI: {video}")
                return video_uri
        raise Veo3Error(f"timeout {TIMEOUT_SECONDS}s")
