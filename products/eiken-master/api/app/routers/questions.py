import json
import random
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models.question import Question
from app.models.user import User
from app.schemas.question import QuestionOut
from app.services import ai_service

router = APIRouter()
SEED_PATH = Path(__file__).parent.parent.parent / "data" / "seed_questions.json"


@router.get("", response_model=list[QuestionOut])
def get_questions(
    skill: str = Query(..., pattern=r"^(reading|listening|writing|speaking)$"),
    count: int = Query(5, ge=1, le=20),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    questions = (
        db.query(Question)
        .filter(Question.grade == user.grade, Question.skill == skill)
        .all()
    )
    if not questions:
        return []
    return random.sample(questions, min(count, len(questions)))


@router.post("/generate", response_model=QuestionOut, status_code=201)
def generate_question(
    skill: str = Query(..., pattern=r"^(reading|listening|writing|speaking)$"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        content = ai_service.generate_question(skill, user.grade)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"問題生成に失敗しました: {e}")
    q = Question(grade=user.grade, skill=skill, source="ai_generated", content=content)
    db.add(q)
    db.commit()
    db.refresh(q)
    return q


@router.post("/seed", status_code=201)
def seed_questions(db: Session = Depends(get_db)):
    """開発用シードエンドポイント。"""
    if not SEED_PATH.exists():
        return {"seeded": 0}
    if db.query(Question).count() > 0:
        return {"seeded": 0, "message": "already seeded"}
    data = json.loads(SEED_PATH.read_text())
    seeded = 0
    for item in data:
        db.add(Question(**{k: v for k, v in item.items() if k != "id"}))
        seeded += 1
    db.commit()
    return {"seeded": seeded}
