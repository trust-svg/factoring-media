from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models.session import QuestionAttempt, StudySession
from app.models.user import User
from app.services import ai_service

router = APIRouter()

JST = timezone(timedelta(hours=9))
SKILLS = ["reading", "listening", "writing", "speaking"]
PASS_THRESHOLD = {"pre2": 0.65, "2": 0.60}
WEIGHTS = {"reading": 0.25, "listening": 0.25, "writing": 0.25, "speaking": 0.25}


@router.get("/progress")
def get_progress(user: User = Depends(current_user), db: Session = Depends(get_db)):
    now = datetime.now(JST)
    today = now.date()
    cutoff14 = now - timedelta(days=14)
    cutoff7 = now - timedelta(days=7)

    # Skill accuracy (last 14 days)
    attempts = (
        db.query(QuestionAttempt)
        .filter(
            QuestionAttempt.user_id == user.id,
            QuestionAttempt.attempted_at >= cutoff14,
        )
        .all()
    )

    skill_breakdown: dict[str, Optional[float]] = {}
    for skill in SKILLS:
        sa = [a for a in attempts if a.skill == skill]
        skill_breakdown[skill] = (
            round(sum(1 for a in sa if a.is_correct) / len(sa), 3) if sa else None
        )

    # Pass probability
    threshold = PASS_THRESHOLD.get(user.grade, 0.65)
    filled = {s: v for s, v in skill_breakdown.items() if v is not None}
    pass_probability: Optional[float] = None
    if filled:
        weighted = sum((filled.get(s) or 0) * w for s, w in WEIGHTS.items())
        pass_probability = round(min(weighted / threshold, 1.0), 3)

    # Trend: last 7 days vs prev 7 days
    recent = [a for a in attempts if a.attempted_at >= cutoff7]
    prev = [a for a in attempts if a.attempted_at < cutoff7]
    if not recent:
        trend = "flat"
    else:
        r_acc = sum(1 for a in recent if a.is_correct) / len(recent)
        p_acc = sum(1 for a in prev if a.is_correct) / len(prev) if prev else r_acc
        if r_acc > p_acc + 0.05:
            trend = "up"
        elif r_acc < p_acc - 0.05:
            trend = "down"
        else:
            trend = "flat"

    # Streak: consecutive days studied ending today
    session_rows = (
        db.query(StudySession.started_at).filter(StudySession.user_id == user.id).all()
    )
    session_dates: set[date] = set()
    for (started_at,) in session_rows:
        if started_at:
            d = started_at.date() if isinstance(started_at, datetime) else started_at
            session_dates.add(d)

    streak = 0
    check = today
    while check in session_dates:
        streak += 1
        check -= timedelta(days=1)

    # Days remaining
    days_remaining: Optional[int] = None
    if user.exam_date:
        days_remaining = max(0, (user.exam_date - today).days)

    # Calendar: last 35 days with study activity
    cal_start = today - timedelta(days=34)
    recent_dates = [
        (cal_start + timedelta(days=i)).isoformat()
        for i in range(35)
        if (cal_start + timedelta(days=i)) in session_dates
    ]

    total_sessions = (
        db.query(StudySession).filter(StudySession.user_id == user.id).count()
    )

    # AI advice + praise (Claude Haiku) — returns None if API unavailable
    advice: Optional[str] = None
    praise: Optional[str] = None
    try:
        advice = ai_service.generate_advice(
            grade=user.grade,
            days_remaining=days_remaining,
            pass_probability=pass_probability,
            skill_breakdown=skill_breakdown,
            streak=streak,
        )
    except Exception:
        pass
    try:
        praise = ai_service.generate_praise_for_progress(
            grade=user.grade,
            streak=streak,
            pass_probability=pass_probability,
        )
    except Exception:
        pass

    return {
        "pass_probability": pass_probability,
        "skill_breakdown": skill_breakdown,
        "streak": streak,
        "trend": trend,
        "days_remaining": days_remaining,
        "total_sessions": total_sessions,
        "grade": user.grade,
        "advice": advice,
        "praise": praise,
        "recent_dates": recent_dates,
    }
