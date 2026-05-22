import json
import logging
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import INTERNAL_TOKEN
from app.db import get_db
from app.deps import current_user
from app.models.question import Question
from app.models.session import QuestionAttempt
from app.models.user import User
from app.schemas.question import QuestionOut
from app.services import ai_service

logger = logging.getLogger(__name__)
router = APIRouter()
SEED_PATH = Path(__file__).parent.parent.parent / "data" / "seed_questions.json"
JST = timezone(timedelta(hours=9))

_GRADES = ["pre2", "2"]
_SKILLS = ["reading", "listening", "writing", "speaking"]
_MIN_PER_COMBO = 15
_SEEN_DAYS = 14


@router.get("", response_model=list[QuestionOut])
def get_questions(
    skill: str = Query(..., pattern=r"^(reading|listening|writing|speaking)$"),
    count: int = Query(5, ge=1, le=20),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    cutoff = datetime.now(JST).replace(tzinfo=None) - timedelta(days=_SEEN_DAYS)
    seen_ids = {
        row.question_id
        for (row,) in db.query(QuestionAttempt.question_id)
        .filter(
            QuestionAttempt.user_id == user.id,
            QuestionAttempt.attempted_at >= cutoff,
        )
        .all()
        if row
    }

    base = db.query(Question).filter(
        Question.grade == user.grade, Question.skill == skill
    )
    unseen = [q for q in base.all() if q.id not in seen_ids]

    if len(unseen) >= count:
        return random.sample(unseen, count)

    # Fallback: fill with seen questions to reach `count`
    all_qs = base.all()
    pool = unseen + [q for q in all_qs if q.id not in {u.id for u in unseen}]
    if not pool:
        return []
    return random.sample(pool, min(count, len(pool)))


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


@router.post("/stock", status_code=201)
def stock_questions(
    x_internal_token: str = Header(default="", alias="X-Internal-Token"),
    db: Session = Depends(get_db),
):
    """各grade×skillの問題数が _MIN_PER_COMBO 未満なら最大3問ずつ生成する。"""
    if INTERNAL_TOKEN and x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    generated = 0
    for grade in _GRADES:
        for skill in _SKILLS:
            current = (
                db.query(Question)
                .filter(Question.grade == grade, Question.skill == skill)
                .count()
            )
            needed = max(0, _MIN_PER_COMBO - current)
            for _ in range(min(needed, 3)):
                try:
                    content = ai_service.generate_question(skill, grade)
                    db.add(
                        Question(
                            grade=grade,
                            skill=skill,
                            source="ai_generated",
                            content=content,
                        )
                    )
                    db.commit()
                    generated += 1
                except Exception:
                    logger.exception(
                        "stock_questions: generate failed grade=%s skill=%s",
                        grade,
                        skill,
                    )
    return {"generated": generated}


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
