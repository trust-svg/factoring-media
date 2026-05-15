from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class SessionStart(BaseModel):
    skill: str = Field(..., pattern=r"^(reading|listening|writing|speaking)$")


class SessionEnd(BaseModel):
    duration_seconds: int = Field(..., ge=0)
    questions_attempted: int = Field(..., ge=0)
    correct_count: int = Field(..., ge=0)
    pomodoro_completed: bool = False


class AttemptCreate(BaseModel):
    question_id: str
    skill: str
    user_answer: Optional[str] = None
    is_correct: bool
    time_spent_seconds: Optional[int] = None


class SessionOut(BaseModel):
    id: str
    skill: str
    started_at: datetime
    duration_seconds: Optional[int] = None
    accuracy_rate: Optional[float] = None
    questions_attempted: int
    pomodoro_completed: bool

    model_config = {"from_attributes": True}
