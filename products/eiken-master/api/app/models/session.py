import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import String, Integer, Float, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

JST = timezone(timedelta(hours=9))


class StudySession(Base):
    __tablename__ = "study_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    skill: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(JST))
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    accuracy_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    questions_attempted: Mapped[int] = mapped_column(Integer, default=0)
    pomodoro_completed: Mapped[bool] = mapped_column(Boolean, default=False)


class QuestionAttempt(Base):
    __tablename__ = "question_attempts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("study_sessions.id"), nullable=False
    )
    question_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("questions.id"), nullable=False
    )
    skill: Mapped[str] = mapped_column(String(20), nullable=False)
    user_answer: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    time_spent_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(JST))
