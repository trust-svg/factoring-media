"""画像・動画生成トリガー API。"""
from __future__ import annotations
import asyncio
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from database import get_session, Job, JobStatus
from core.patterns import get_batch_prompts, PATTERNS, is_blocked
from core.image_gen import generate_image
from core.notifier import notify_images_ready
from config import PENDING_DIR

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


class SingleGenerateRequest(BaseModel):
    pattern: str
    custom_prompt: str | None = None


@router.post("/generate/batch")
async def generate_batch(background_tasks: BackgroundTasks):
    """月バッチ: ABパターン各2本ずつ計10本の画像を生成する。"""
    prompts = get_batch_prompts()
    job_ids = []
    with get_session() as session:
        for item in prompts:
            job = Job(
                pattern=item["pattern"],
                prompt=item["video_prompt"],
                status=JobStatus.PENDING,
            )
            session.add(job)
            session.flush()
            job_ids.append((job.id, item["image_prompt"], item["video_prompt"]))
        session.commit()

    background_tasks.add_task(_run_batch_image_gen, job_ids)
    return {"status": "started", "job_count": len(job_ids)}


@router.post("/generate/image")
async def generate_single_image(req: SingleGenerateRequest, background_tasks: BackgroundTasks):
    """都度生成: 1本の画像を生成する。"""
    if req.pattern not in PATTERNS:
        raise HTTPException(status_code=400, detail=f"Invalid pattern: {req.pattern}")
    pattern = PATTERNS[req.pattern]
    image_prompt = req.custom_prompt or pattern["image_prompt"]
    if is_blocked(image_prompt):
        raise HTTPException(status_code=400, detail="ブロックワードが含まれています")

    with get_session() as session:
        job = Job(pattern=req.pattern, prompt=pattern["video_prompt"], status=JobStatus.PENDING)
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
        await asyncio.sleep(2.0)  # rate limit対策

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
