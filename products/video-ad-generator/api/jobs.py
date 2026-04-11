"""ジョブ一覧・統計 API。"""
from __future__ import annotations
from fastapi import APIRouter
from sqlalchemy import func
from database import get_session, Job, JobStatus

router = APIRouter(prefix="/api")


@router.get("/jobs")
def list_jobs(status: str | None = None, limit: int = 50):
    with get_session() as session:
        query = session.query(Job).order_by(Job.created_at.desc())
        if status:
            query = query.filter(Job.status == status)
        jobs = query.limit(limit).all()
        return [_job_to_dict(j) for j in jobs]


@router.get("/jobs/{job_id}")
def get_job(job_id: int):
    with get_session() as session:
        job = session.get(Job, job_id)
        if not job:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Job not found")
        return _job_to_dict(job)


@router.get("/stats")
def get_stats():
    with get_session() as session:
        total = session.query(func.count(Job.id)).scalar()
        done = session.query(func.count(Job.id)).filter(Job.status == JobStatus.DONE).scalar()
        total_cost = session.query(
            func.sum(Job.image_cost_usd + Job.video_cost_usd)
        ).scalar() or 0.0
        return {
            "total_jobs": total,
            "done": done,
            "pending_approval": session.query(func.count(Job.id)).filter(
                Job.status == JobStatus.PENDING
            ).scalar(),
            "total_cost_usd": round(total_cost, 4),
        }


def _job_to_dict(job: Job) -> dict:
    return {
        "id": job.id,
        "pattern": job.pattern,
        "status": job.status,
        "image_path": job.image_path,
        "video_path": job.video_path,
        "image_cost_usd": job.image_cost_usd,
        "video_cost_usd": job.video_cost_usd,
        "auto_score": job.auto_score,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }
