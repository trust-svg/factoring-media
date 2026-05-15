# products/eiken-master/api/app/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models.user import User
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    UpdateUserRequest,
    UserOut,
)
from app.services.auth import hash_pin, verify_pin, create_token

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")
    user = User(
        username=body.username,
        pin_hash=hash_pin(body.pin),
        grade=body.grade,
        exam_date=body.exam_date,
        daily_goal_minutes=body.daily_goal_minutes,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenResponse(
        access_token=create_token(user.id), user_id=user.id, grade=user.grade
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_pin(body.pin, user.pin_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenResponse(
        access_token=create_token(user.id), user_id=user.id, grade=user.grade
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return UserOut(
        id=str(user.id),
        username=user.username,
        grade=user.grade,
        exam_date=user.exam_date,
        daily_goal_minutes=user.daily_goal_minutes,
    )


@router.put("/me", response_model=UserOut)
def update_me(
    body: UpdateUserRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if body.grade is not None:
        user.grade = body.grade
    if "exam_date" in body.model_fields_set:
        user.exam_date = body.exam_date
    if body.daily_goal_minutes is not None:
        user.daily_goal_minutes = body.daily_goal_minutes
    db.commit()
    db.refresh(user)
    return UserOut(
        id=str(user.id),
        username=user.username,
        grade=user.grade,
        exam_date=user.exam_date,
        daily_goal_minutes=user.daily_goal_minutes,
    )
