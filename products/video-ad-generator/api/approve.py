"""承認・却下 API。"""

from __future__ import annotations
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks
from database import get_session, Job, JobStatus
from config import PENDING_DIR, APPROVED_DIR, REJECTED_DIR, VIDEOS_DIR
from core.video_providers import get_provider, VideoGenRequest
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

        # アップロード画像はファイル移動しない（uploaded フォルダ維持）
        if job.image_source == "generated" and job.image_path:
            src = Path(job.image_path)
            dst = APPROVED_DIR / src.name
            if src.exists():
                src.rename(dst)
            job.image_path = str(dst)

        session.commit()
        snap = {
            "id": job.id,
            "image_path": job.image_path,
            "video_prompt": job.prompt,
            "provider": job.provider,
            "aspect_ratio": job.aspect_ratio,
            "duration_seconds": job.duration_seconds,
            "camera_preset": job.camera_preset,
            "quality": job.quality,
            "pattern": job.pattern,
        }

    background_tasks.add_task(_run_video_gen, snap)
    return {"status": "approved", "job_id": job_id}


@router.post("/reject/{job_id}")
def reject_job(job_id: int):
    with get_session() as session:
        job = session.get(Job, job_id)
        if not job or job.status != JobStatus.PENDING:
            raise HTTPException(status_code=404, detail="Job not found or not pending")
        job.status = JobStatus.REJECTED
        if job.image_path and job.image_source == "generated":
            src = Path(job.image_path)
            dst = REJECTED_DIR / src.name
            if src.exists():
                src.rename(dst)
            job.image_path = str(dst)
        session.commit()
    return {"status": "rejected", "job_id": job_id}


def _set_stage(job_id: int, stage: str | None) -> None:
    with get_session() as session:
        job = session.get(Job, job_id)
        if job:
            job.video_progress_stage = stage
            session.commit()


async def _run_video_gen(snap: dict):
    job_id = snap["id"]
    output_path = VIDEOS_DIR / f"job_{job_id}.mp4"

    with get_session() as session:
        job = session.get(Job, job_id)
        if job:
            job.status = JobStatus.VIDEO_GENERATING
            job.video_progress_stage = None
            session.commit()

    try:
        provider = get_provider(snap["provider"])
        req = VideoGenRequest(
            image_path=Path(snap["image_path"]),
            video_prompt=snap["video_prompt"],
            aspect_ratio=snap["aspect_ratio"],
            duration_seconds=snap["duration_seconds"],
            camera_preset=snap["camera_preset"],
            quality=snap["quality"],
            output_path=output_path,
        )
        provider.validate(req)
        cost = provider.calc_cost(req)

        await provider.generate(req, progress_callback=lambda s: _set_stage(job_id, s))
        _set_stage(job_id, None)

        with get_session() as session:
            job = session.get(Job, job_id)
            if job:
                job.status = JobStatus.DONE
                job.video_path = str(output_path)
                job.video_cost_usd = cost
                job.video_cost_calc_basis = provider.cost_basis
                session.commit()
                pattern_or_provider = snap.get("pattern") or snap["provider"]
                await notify_video_done(pattern_or_provider, job_id)
    except Exception as e:
        logger.error(f"Job {job_id} 動画生成失敗: {e}")
        stage = None
        with get_session() as session:
            job = session.get(Job, job_id)
            if job:
                stage = job.video_progress_stage
                job.status = JobStatus.FAILED
                job.error_message = str(e)[:1000]
                session.commit()
        await notify_job_failed(job_id, f"[{stage or 'unknown'}] {e}")
