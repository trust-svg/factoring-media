"""HTTP client for the video-analyzer service.

video-analyzer is a separate FastAPI service hosted at config.VIDEO_ANALYZER_URL.
This module wraps the three endpoints d-manager needs:

- POST /analyze                              → full structured analysis
- GET  /analysis/{row_id}/transcript         → full transcript (on-demand)
- GET  /analysis/{row_id}/keyframes?n=N      → base64-encoded keyframes
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

import config

logger = logging.getLogger(__name__)


def _base_url() -> str:
    url = (config.VIDEO_ANALYZER_URL or "").rstrip("/")
    if not url:
        raise RuntimeError("VIDEO_ANALYZER_URL is not configured")
    return url


def _headers() -> dict[str, str]:
    key = config.VIDEO_ANALYZER_API_KEY or ""
    if not key:
        raise RuntimeError("VIDEO_ANALYZER_API_KEY is not configured")
    return {"X-API-Key": key, "Content-Type": "application/json"}


async def analyze(
    url: str, force: bool = False, timeout: float = 180.0
) -> dict[str, Any]:
    """Run the full pipeline. Returns the AnalyzeResponse dict.

    On HTTP 429 (daily budget exceeded) the caller should surface a friendly
    message rather than retry — re-raising httpx.HTTPStatusError preserves the
    detail for the caller to read.
    """
    payload = {"url": url, "force": force}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{_base_url()}/analyze", json=payload, headers=_headers()
        )
        resp.raise_for_status()
        return resp.json()


async def get_transcript(row_id: int, timeout: float = 30.0) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(
            f"{_base_url()}/analysis/{row_id}/transcript", headers=_headers()
        )
        resp.raise_for_status()
        return resp.json()


async def get_keyframes(
    row_id: int, n: int = 3, timeout: float = 60.0
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(
            f"{_base_url()}/analysis/{row_id}/keyframes",
            params={"n": n},
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.json()
