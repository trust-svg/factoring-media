# products/eiken-master/api/app/schemas/auth.py
from datetime import date
from typing import Optional

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


class UserOut(BaseModel):
    id: str
    username: str
    grade: str
    exam_date: Optional[date]
    daily_goal_minutes: int
