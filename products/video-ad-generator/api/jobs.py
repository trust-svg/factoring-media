"""ジョブ一覧・統計 API。"""

from __future__ import annotations
from fastapi import APIRouter, Query
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


@router.get("/jobs/cost-summary")
def cost_summary(
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
):
    """期間内の動画コストを provider 別に集計する。
    from / to は YYYY-MM-DD 形式。省略時は全期間。
    """
    from datetime import datetime

    with get_session() as session:
        q = session.query(
            Job.provider, func.count(Job.id), func.sum(Job.video_cost_usd)
        ).group_by(Job.provider)
        if from_:
            from_dt = datetime.fromisoformat(from_)
            q = q.filter(Job.created_at >= from_dt)
        if to:
            to_dt = datetime.fromisoformat(to + " 23:59:59" if "T" not in to else to)
            q = q.filter(Job.created_at <= to_dt)
        rows = q.all()

    by_provider = [
        {"provider": p or "unknown", "count": c, "total_usd": round(s or 0.0, 4)}
        for p, c, s in rows
    ]
    total = round(sum(p["total_usd"] for p in by_provider), 4)
    return {
        "total_video_cost_usd": total,
        "by_provider": by_provider,
        "note": "概算値です。muapi.ai ダッシュボードで実額を確認してください。",
    }


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
        done = (
            session.query(func.count(Job.id))
            .filter(Job.status == JobStatus.DONE)
            .scalar()
        )
        total_cost = (
            session.query(func.sum(Job.image_cost_usd + Job.video_cost_usd)).scalar()
            or 0.0
        )
        return {
            "total_jobs": total,
            "done": done,
            "pending_approval": session.query(func.count(Job.id))
            .filter(Job.status == JobStatus.PENDING)
            .scalar(),
            "total_cost_usd": round(total_cost, 4),
        }


def _job_to_dict(job: Job) -> dict:
    return {
        "id": job.id,
        "pattern": job.pattern,
        "template_id": job.template_id,
        "provider": job.provider,
        "aspect_ratio": job.aspect_ratio,
        "duration_seconds": job.duration_seconds,
        "camera_preset": job.camera_preset,
        "image_source": job.image_source,
        "status": job.status,
        "image_path": job.image_path,
        "video_path": job.video_path,
        "image_cost_usd": job.image_cost_usd,
        "video_cost_usd": job.video_cost_usd,
        "video_cost_calc_basis": job.video_cost_calc_basis,
        "video_progress_stage": job.video_progress_stage,
        "auto_score": job.auto_score,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }
