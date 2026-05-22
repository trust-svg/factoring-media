import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.db import SessionLocal, get_db
from app.deps import current_user
from app.models.session import StudySession, QuestionAttempt
from app.models.user import User
from app.schemas.session import SessionStart, SessionEnd, AttemptCreate, SessionOut
from app.services import telegram

logger = logging.getLogger(__name__)
router = APIRouter()


def _categorize_error_bg(attempt_id: str, skill: str, question_content: dict) -> None:
    """Run in background: call Claude to assign a specific error category."""
    from app.services import ai_service

    db = SessionLocal()
    try:
        category = ai_service.categorize_error(skill, question_content)
        attempt = (
            db.query(QuestionAttempt).filter(QuestionAttempt.id == attempt_id).first()
        )
        if attempt:
            attempt.error_category = category
            db.commit()
    except Exception:
        logger.exception("_categorize_error_bg failed for attempt_id=%s", attempt_id)
    finally:
        db.close()


@router.post("/start", response_model=SessionOut, status_code=201)
def start_session(
    body: SessionStart,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
):
    session = StudySession(user_id=user.id, skill=body.skill)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.post("/{session_id}/end", response_model=SessionOut)
def end_session(
    session_id: str,
    body: SessionEnd,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
):
    session = (
        db.query(StudySession)
        .filter(StudySession.id == session_id, StudySession.user_id == user.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    accuracy = (
        body.correct_count / body.questions_attempted
        if body.questions_attempted > 0
        else None
    )
    session.duration_seconds = body.duration_seconds
    session.questions_attempted = body.questions_attempted
    session.accuracy_rate = accuracy
    session.pomodoro_completed = body.pomodoro_completed
    db.commit()
    db.refresh(session)

    return session


@router.post("/notify-complete", status_code=200)
def notify_complete(
    background_tasks: BackgroundTasks,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
):
    """Called by frontend when all daily tasks are done. Sends one Telegram notification."""
    from datetime import date, datetime, timedelta, timezone

    JST = timezone(timedelta(hours=9))
    today = datetime.now(JST).date()
    session_dates: set[date] = set()
    for (s,) in (
        db.query(StudySession.started_at).filter(StudySession.user_id == user.id).all()
    ):
        if s:
            session_dates.add(s.date() if isinstance(s, datetime) else s)
    streak = 0
    check = today
    while check in session_dates:
        streak += 1
        check -= timedelta(days=1)

    background_tasks.add_task(
        telegram.send_daily_complete,
        username=user.username,
        streak=streak,
    )
    return {"ok": True}


@router.post("/{session_id}/attempt", status_code=201)
def record_attempt(
    session_id: str,
    body: AttemptCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
):
    session = (
        db.query(StudySession)
        .filter(StudySession.id == session_id, StudySession.user_id == user.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Static fallback category; AI will overwrite for reading/listening wrong answers
    _STATIC_CATEGORIES = {
        "writing": "writing_expression",
        "speaking": "speaking_expression",
    }
    error_category = _STATIC_CATEGORIES.get(body.skill) if not body.is_correct else None

    attempt = QuestionAttempt(
        user_id=user.id,
        session_id=session_id,
        question_id=body.question_id,
        skill=body.skill,
        user_answer=body.user_answer,
        is_correct=body.is_correct,
        error_category=error_category,
        time_spent_seconds=body.time_spent_seconds,
    )
    db.add(attempt)
    db.commit()

    # Fire AI categorization in background for reading/listening wrong answers
    if not body.is_correct and body.skill in ("reading", "listening"):
        from app.models.question import Question

        q = db.query(Question).filter(Question.id == body.question_id).first()
        q_content = q.content if q else {}
        background_tasks.add_task(
            _categorize_error_bg, attempt.id, body.skill, q_content
        )

    return {"id": attempt.id}
