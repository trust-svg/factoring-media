"""Atlas Cloud Seedance 2.0 I2V API クライアント。
承認済み画像を10秒の9:16動画に変換する。
画像はTelegramにアップロードして安定した公開URLを取得する。
"""
from __future__ import annotations
import asyncio
import logging
from pathlib import Path
import httpx
from config import (
    ATLAS_CLOUD_API_KEY,
    ATLAS_CLOUD_I2V_URL,
    ATLAS_CLOUD_STATUS_URL,
    VIDEO_DURATION,
    VIDEO_ASPECT_RATIO,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
POLL_INTERVAL = 15.0
TIMEOUT_SECONDS = 900.0  # 15分


class VideoGenError(Exception):
    pass


async def _upload_image_to_telegram(image_path: Path) -> str:
    """画像をTelegramにアップロードして公開ダウンロードURLを返す。"""
    base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        with open(image_path, "rb") as f:
            resp = await client.post(
                f"{base_url}/sendDocument",
                data={"chat_id": TELEGRAM_CHAT_ID},
                files={"document": (image_path.name, f, "image/jpeg")},
            )
        resp.raise_for_status()
        result = resp.json()
        file_id = result["result"]["document"]["file_id"]

        resp2 = await client.get(f"{base_url}/getFile", params={"file_id": file_id})
        resp2.raise_for_status()
        file_path = resp2.json()["result"]["file_path"]

        download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
        logger.info(f"Telegram upload OK: {download_url}")
        return download_url


async def generate_video(image_path: Path, video_prompt: str, output_path: Path) -> Path:
    """Seedance 2.0 I2V で動画を生成して output_path に保存する。"""
    headers = {
        "x-api-key": ATLAS_CLOUD_API_KEY,
        "Content-Type": "application/json",
    }

    # 画像をTelegramにアップロードして安定したURLを取得
    image_url = await _upload_image_to_telegram(image_path)
    logger.info(f"使用する画像URL: {image_url}")

    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=60.0) as client:
        payload = {
            "prompt": video_prompt,
            "images_list": [image_url],
            "aspect_ratio": VIDEO_ASPECT_RATIO,
            "duration": VIDEO_DURATION,
            "quality": "basic",
        }
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

                resp_data = resp.json()
                logger.info(f"動画生成APIレスポンス全体: {resp_data}")
                request_id = resp_data["request_id"]
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
    """ステータスが完了になるまでポーリング。video URLを返す。"""
    status_url = ATLAS_CLOUD_STATUS_URL.format(request_id=request_id)
    elapsed = 0.0
    while elapsed < TIMEOUT_SECONDS:
        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        resp = await client.get(status_url, headers=headers)
        logger.info(f"ポーリング HTTP {resp.status_code} ({elapsed:.0f}s): {resp.text[:300]}")
        if resp.status_code == 404:
            raise VideoGenError(f"ステータスURL 404: {status_url}")
        data = resp.json()
        status = data.get("status")
        # outputs 配列（Atlas Cloud 形式）または output_url 形式に対応
        outputs = data.get("outputs") or []
        output_url = outputs[0] if outputs else (data.get("output_url") or data.get("video_url"))
        if status in ("done", "succeeded", "completed", "success"):
            if output_url:
                return output_url
            raise VideoGenError(f"完了ステータスだが動画URLが見つからない: {data}")
        if status in ("failed", "error", "cancelled"):
            raise VideoGenError(f"Atlas Cloud でジョブ失敗: {data}")
        logger.info(f"ポーリング中 ({elapsed:.0f}s): status={status}")
    raise VideoGenError(f"タイムアウト: {TIMEOUT_SECONDS}秒以内に完了しなかった")
