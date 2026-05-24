# products/eiken-master/api/app/schemas/auth.py
import json
from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    pin: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")
    grade: str = Field(..., pattern=r"^(pre2|2)$")
    exam_date: Optional[date] = None
    daily_goal_minutes: int = Field(30, ge=5, le=120)


class LoginRequest(BaseModel):
    username: str
    pin: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    grade: str


class UpdateUserRequest(BaseModel):
    grade: Optional[str] = Field(None, pattern=r"^(pre2|2)$")
    exam_date: Optional[date] = None
    daily_goal_minutes: Optional[int] = Field(None, ge=5, le=120)
    reminder_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    reminder_days: Optional[List[int]] = None
    # reminder_schedule supersedes reminder_time + reminder_days
    # format: {"0": "20:00", "2": "21:00", ...}  key=weekday(0=Mon), value=HH:MM
    reminder_schedule: Optional[dict] = None
    study_days: Optional[List[int]] = None  # weekday indices (0=Mon … 6=Sun)


class UserOut(BaseModel):
    id: str
    username: str
    grade: str
    exam_date: Optional[date]
    daily_goal_minutes: int
    reminder_time: str = "20:00"
    reminder_days: List[int] = Field(default_factory=lambda: list(range(7)))
    reminder_schedule: Optional[dict] = None
    study_days: List[int] = Field(default_factory=lambda: list(range(7)))
