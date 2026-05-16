import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models.session import StudySession
from app.models.user import User
from app.services import ai_service

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_skill_breakdown(user_id, db: Session) -> dict:
    from sqlalchemy import func
    from datetime import timedelta

    cutoff = date.today() - timedelta(days=14)
    rows = (
        db.query(StudySession.skill, func.avg(StudySession.accuracy_rate))
        .filter(
            StudySession.user_id == user_id,
            StudySession.accuracy_rate.isnot(None),
            StudySession.started_at >= cutoff,
        )
        .group_by(StudySession.skill)
        .all()
    )
    return {skill: float(avg) for skill, avg in rows}


@router.get("/today")
def get_today_plan(user: User = Depends(current_user), db: Session = Depends(get_db)):
    days_remaining: int | None = None
    if user.exam_date:
        delta = user.exam_date - date.today()
        days_remaining = max(0, delta.days)

    skill_breakdown = _get_skill_breakdown(user.id, db)

    try:
        plan = ai_service.generate_daily_plan(
            grade=user.grade,
            days_remaining=days_remaining,
            daily_minutes=user.daily_goal_minutes,
            skill_breakdown=skill_breakdown,
        )
    except Exception:
        logger.exception("generate_daily_plan failed")
        raise HTTPException(status_code=502, detail="プラン生成に失敗しました")

    return plan
