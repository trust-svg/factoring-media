"""画像・動画生成トリガー API。"""

from __future__ import annotations
import asyncio
import logging
from typing import Literal
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from database import get_session, Job, JobStatus, Template
from core.patterns import get_batch_prompts, PATTERNS
from core.safety import is_blocked
from core.image_gen import generate_image
from core.notifier import notify_images_ready
from config import PENDING_DIR

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


class SingleGenerateRequest(BaseModel):
    pattern: str | None = None
    custom_prompt: str | None = None
    template_id: int | None = None
    image_prompt: str | None = None
    video_prompt: str | None = None
    provider: str | None = None
    aspect_ratio: Literal["9:16", "16:9", "1:1", "4:3", "3:4", "21:9"] | None = None
    duration_seconds: int | None = None
    camera_preset: str | None = None
    image_source: str = "generated"
    quality: Literal["low", "high"] | None = None


@router.post("/generate/batch")
async def generate_batch(background_tasks: BackgroundTasks):
    prompts = get_batch_prompts()
    job_ids = []
    with get_session() as session:
        for item in prompts:
            job = Job(
                pattern=item["pattern"],
                prompt=item["video_prompt"],
                provider="seedance",
                aspect_ratio="9:16",
                duration_seconds=10,
                camera_preset=None,
                image_source="generated",
                status=JobStatus.PENDING,
            )
            session.add(job)
            session.flush()
            job_ids.append((job.id, item["image_prompt"], item["video_prompt"]))
        session.commit()

    background_tasks.add_task(_run_batch_image_gen, job_ids)
    return {"status": "started", "job_count": len(job_ids)}


@router.post("/generate/image")
async def generate_single_image(
    req: SingleGenerateRequest, background_tasks: BackgroundTasks
):
    image_prompt: str | None = None
    video_prompt: str | None = None
    provider = req.provider or "seedance"
    aspect_ratio = req.aspect_ratio or "9:16"
    duration_seconds = req.duration_seconds if req.duration_seconds is not None else 10
    camera_preset = req.camera_preset
    template_id = req.template_id
    quality = req.quality or "low"

    if req.template_id is not None:
        with get_session() as session:
            tmpl = session.get(Template, req.template_id)
            if not tmpl:
                raise HTTPException(status_code=404, detail="Template not found")
            image_prompt = req.image_prompt or tmpl.image_prompt
            video_prompt = req.video_prompt or tmpl.video_prompt
            provider = req.provider or tmpl.default_provider
            aspect_ratio = req.aspect_ratio or tmpl.default_aspect
            duration_seconds = (
                req.duration_seconds
                if req.duration_seconds is not None
                else tmpl.default_duration
            )
            camera_preset = req.camera_preset or tmpl.default_camera_preset
            quality = req.quality or tmpl.default_quality
    elif req.pattern is not None:
        if req.pattern not in PATTERNS:
            raise HTTPException(
                status_code=400, detail=f"Invalid pattern: {req.pattern}"
            )
        pattern = PATTERNS[req.pattern]
        image_prompt = req.custom_prompt or req.image_prompt or pattern["image_prompt"]
        video_prompt = req.video_prompt or pattern["video_prompt"]
    else:
        image_prompt = req.image_prompt
        video_prompt = req.video_prompt
        if not image_prompt or not video_prompt:
            raise HTTPException(
                status_code=400, detail="image_prompt と video_prompt が必要です"
            )

    if image_prompt is None or video_prompt is None:
        raise HTTPException(
            status_code=400, detail="image_prompt と video_prompt が必要です"
        )

    if is_blocked(image_prompt) or is_blocked(video_prompt):
        raise HTTPException(
            status_code=400, detail="プロンプトにブロックワードが含まれています"
        )

    with get_session() as session:
        job = Job(
            pattern=req.pattern,
            template_id=template_id,
            prompt=video_prompt,
            provider=provider,
            aspect_ratio=aspect_ratio,
            duration_seconds=duration_seconds,
            camera_preset=camera_preset,
            image_source=req.image_source,
            quality=quality,
            status=JobStatus.PENDING,
        )
        session.add(job)
        session.flush()
        job_id = job.id
        session.commit()

    background_tasks.add_task(_run_single_image_gen, job_id, image_prompt)
    return {"status": "started", "job_id": job_id}


async def _run_batch_image_gen(job_ids: list[tuple[int, str, str]]):
    successful = 0
    for job_id, image_prompt, _ in job_ids:
        output_path = PENDING_DIR / f"job_{job_id}.jpg"
        try:
            await generate_image(prompt=image_prompt, output_path=output_path)
            with get_session() as session:
                job = session.get(Job, job_id)
                if job:
                    job.image_path = str(output_path)
                    session.commit()
            successful += 1
        except Exception as e:
            logger.error(f"Job {job_id} 画像生成失敗: {e}")
            with get_session() as session:
                job = session.get(Job, job_id)
                if job:
                    job.status = JobStatus.FAILED
                    job.error_message = str(e)[:1000]
                    session.commit()
        await asyncio.sleep(2.0)

    await notify_images_ready(successful)


async def _run_single_image_gen(job_id: int, image_prompt: str):
    output_path = PENDING_DIR / f"job_{job_id}.jpg"
    try:
        await generate_image(prompt=image_prompt, output_path=output_path)
        with get_session() as session:
            job = session.get(Job, job_id)
            if job:
                job.image_path = str(output_path)
                session.commit()
    except Exception as e:
        logger.error(f"Job {job_id} 画像生成失敗: {e}")
        with get_session() as session:
            job = session.get(Job, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(e)[:1000]
                session.commit()
