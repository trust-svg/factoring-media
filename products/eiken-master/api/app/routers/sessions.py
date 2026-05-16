from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.db import get_db
from app.deps import current_user
from app.models.session import StudySession, QuestionAttempt
from app.models.user import User
from app.schemas.session import SessionStart, SessionEnd, AttemptCreate, SessionOut

router = APIRouter()


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


@router.post("/{session_id}/attempt", status_code=201)
def record_attempt(
    session_id: str,
    body: AttemptCreate,
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

    _ERROR_CATEGORIES = {
        "reading": "reading_comprehension",
        "listening": "listening_comprehension",
        "writing": "writing_expression",
        "speaking": "speaking_expression",
    }
    error_category = _ERROR_CATEGORIES.get(body.skill) if not body.is_correct else None

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
    return {"id": attempt.id}
