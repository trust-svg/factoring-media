"""承認・却下 API。"""
from __future__ import annotations
import asyncio
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks
from database import get_session, Job, JobStatus
from config import PENDING_DIR, APPROVED_DIR, REJECTED_DIR
from core.video_gen import generate_video
from core.notifier import notify_video_done, notify_job_failed

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


@router.post("/approve/{job_id}")
async def approve_job(job_id: int, background_tasks: BackgroundTasks):
    with get_session() as session:
        job = session.get(Job, job_id)
        if not job or job.status != JobStatus.PENDING:
            raise HTTPException(status_code=404, detail="Job not found or not pending")
        job.status = JobStatus.APPROVED
        # pending → approved にファイル移動
        if job.image_path:
            src = Path(job.image_path)
            dst = APPROVED_DIR / src.name
            if src.exists():
                src.rename(dst)
            job.image_path = str(dst)
        session.commit()
        job_id_snap = job.id
        image_path_snap = job.image_path
        video_prompt_snap = job.prompt

    background_tasks.add_task(_run_video_gen, job_id_snap, image_path_snap, video_prompt_snap)
    return {"status": "approved", "job_id": job_id}


@router.post("/reject/{job_id}")
def reject_job(job_id: int):
    with get_session() as session:
        job = session.get(Job, job_id)
        if not job or job.status != JobStatus.PENDING:
            raise HTTPException(status_code=404, detail="Job not found or not pending")
        job.status = JobStatus.REJECTED
        if job.image_path:
            src = Path(job.image_path)
            dst = REJECTED_DIR / src.name
            if src.exists():
                src.rename(dst)
            job.image_path = str(dst)
        session.commit()
    return {"status": "rejected", "job_id": job_id}


async def _run_video_gen(job_id: int, image_path: str, video_prompt: str):
    """バックグラウンドで動画生成を実行する。"""
    from config import VIDEOS_DIR
    output_path = VIDEOS_DIR / f"job_{job_id}.mp4"

    with get_session() as session:
        job = session.get(Job, job_id)
        if job:
            job.status = JobStatus.VIDEO_GENERATING
            session.commit()

    try:
        await generate_video(
            image_path=Path(image_path),
            video_prompt=video_prompt,
            output_path=output_path,
        )
        with get_session() as session:
            job = session.get(Job, job_id)
            if job:
                job.status = JobStatus.DONE
                job.video_path = str(output_path)
                job.video_cost_usd = 0.81  # 10秒 × $0.081/s
                session.commit()
                await notify_video_done(job.pattern, job_id)
    except Exception as e:
        logger.error(f"Job {job_id} 動画生成失敗: {e}")
        with get_session() as session:
            job = session.get(Job, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(e)[:1000]
                session.commit()
        await notify_job_failed(job_id, str(e))
