"""画像アップロード API。"""

from __future__ import annotations

import io
import logging
from pathlib import Path

import config
from core.safety import is_blocked
from database import Job, JobStatus, get_session
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from PIL import Image

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ALLOWED_MIME = {"image/jpeg", "image/png"}
MIN_DIM = 256
MAX_DIM = 4096


@router.post("/upload-image", status_code=201)
async def upload_image(
    file: UploadFile = File(...),
    video_prompt: str = Form(...),
    provider: str = Form(...),
    aspect_ratio: str = Form(...),
    duration_seconds: int = Form(...),
    camera_preset: str | None = Form(None),
    template_id: int | None = Form(None),
):
    # 拡張子チェック
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="対応形式は jpg/png のみ")

    # MIME チェック
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="画像ファイルではありません")

    # サイズチェック
    content = await file.read()
    max_bytes = config.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"画像が大きすぎます（最大{config.MAX_UPLOAD_SIZE_MB}MB）",
        )

    # 中身検証 + 解像度チェック
    try:
        img = Image.open(io.BytesIO(content))
        img.verify()
        img = Image.open(io.BytesIO(content))  # verify は close するため再open
    except Exception:
        raise HTTPException(status_code=400, detail="画像ファイルではありません")

    if img.width < MIN_DIM or img.height < MIN_DIM:
        raise HTTPException(
            status_code=400, detail=f"解像度は{MIN_DIM}〜{MAX_DIM}pxの範囲"
        )
    if img.width > MAX_DIM or img.height > MAX_DIM:
        raise HTTPException(
            status_code=400, detail=f"解像度は{MIN_DIM}〜{MAX_DIM}pxの範囲"
        )

    # プロンプト安全性
    if is_blocked(video_prompt):
        raise HTTPException(
            status_code=400, detail="プロンプトにブロックワードが含まれています"
        )

    # ジョブ作成
    with get_session() as session:
        job = Job(
            template_id=template_id,
            prompt=video_prompt,
            provider=provider,
            aspect_ratio=aspect_ratio,
            duration_seconds=duration_seconds,
            camera_preset=camera_preset,
            image_source="uploaded",
            status=JobStatus.PENDING,
            image_cost_usd=0.0,
        )
        session.add(job)
        session.flush()
        job_id = job.id

        # ファイル保存
        config.UPLOADED_DIR.mkdir(parents=True, exist_ok=True)
        save_path = config.UPLOADED_DIR / f"job_{job_id}{ext}"
        save_path.write_bytes(content)
        job.image_path = str(save_path)
        session.commit()

    return {"job_id": job_id, "status": "PENDING", "image_path": str(save_path)}
