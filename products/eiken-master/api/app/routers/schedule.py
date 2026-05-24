import json
import logging
import time
from datetime import date, timezone, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models.session import StudySession
from app.models.user import User
from app.services import ai_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Cache AI-generated daily plan per user (TTL = rest of the day, min 1h)
_plan_cache: dict[str, tuple[float, dict]] = {}
_PLAN_CACHE_TTL = 8 * 3600  # 8 hours

_STATIC_PLAN = {
    "pre2": {
        "message": "ホーホー！今日も75分しっかり練習していこうね！ライティングとリーディングを重点的にやろう！",
        "tasks": [
            {
                "skill": "writing",
                "description": "英作文練習（25語以上）",
                "minutes": 25,
            },
            {"skill": "reading", "description": "長文読解練習", "minutes": 20},
            {"skill": "listening", "description": "リスニング問題", "minutes": 15},
            {"skill": "flashcards", "description": "単語カード復習", "minutes": 10},
            {"skill": "speaking", "description": "スピーキング練習", "minutes": 5},
        ],
    },
    "2": {
        "message": "ホーホー！2級合格に向けて75分しっかりがんばろうね！スピーキングと読解を中心に！",
        "tasks": [
            {"skill": "speaking", "description": "2分間スピーチ練習", "minutes": 20},
            {"skill": "reading", "description": "長文読解・語彙問題", "minutes": 20},
            {"skill": "listening", "description": "リスニング問題", "minutes": 15},
            {
                "skill": "writing",
                "description": "英作文練習（80〜100語）",
                "minutes": 10,
            },
            {"skill": "flashcards", "description": "単語カード復習", "minutes": 10},
        ],
    },
}


def _get_skill_breakdown(user_id, db: Session) -> dict:
    from datetime import timedelta

    from sqlalchemy import func

    cutoff = date.today() - timedelta(days=14)
    rows = (
        db.query(StudySession.skill, func.avg(StudySession.accuracy_rate))
        .filter(
            StudySession.user_id == user_id,
            StudySession.accuracy_rate.isnot(None),
            StudySession.started_at >= cutoff,
        )
        .group_by(StudySession.skill)
        .all()
    )
    return {skill: float(avg) for skill, avg in rows}


_JST = timezone(timedelta(hours=9))

_REST_DAY_PLAN = {
    "pre2": {
        "message": "ホーホー！今日はお休みの日だよ！ゆっくり休んで、次の勉強日に全力でがんばろうね！",
        "tasks": [],
        "rest_day": True,
    },
    "2": {
        "message": "ホーホー！今日はお休みの日だよ！しっかり休息をとることも合格への大事な一歩だよ！",
        "tasks": [],
        "rest_day": True,
    },
}


def _get_study_days(user: User) -> list[int]:
    try:
        return json.loads(user.study_days or "[0,1,2,3,4,5,6]")
    except (json.JSONDecodeError, TypeError):
        return list(range(7))


@router.get("/today")
def get_today_plan(user: User = Depends(current_user), db: Session = Depends(get_db)):
    today_jst = date.today()  # VPS TZ=Asia/Tokyo なのでホストTZがJST
    study_days = _get_study_days(user)
    if today_jst.weekday() not in study_days:
        return _REST_DAY_PLAN.get(user.grade, _REST_DAY_PLAN["pre2"])

    days_remaining: int | None = None
    if user.exam_date:
        delta = user.exam_date - today_jst
        days_remaining = max(0, delta.days)

    skill_breakdown = _get_skill_breakdown(user.id, db)

    user_id_str = str(user.id)
    now_ts = time.time()
    cached = _plan_cache.get(user_id_str)
    if cached and now_ts - cached[0] < _PLAN_CACHE_TTL:
        return cached[1]

    try:
        plan = ai_service.generate_daily_plan(
            grade=user.grade,
            days_remaining=days_remaining,
            daily_minutes=user.daily_goal_minutes,
            skill_breakdown=skill_breakdown,
        )
        _plan_cache[user_id_str] = (now_ts, plan)
        return plan
    except Exception:
        logger.exception("generate_daily_plan failed, returning static plan")
        return _STATIC_PLAN.get(user.grade, _STATIC_PLAN["pre2"])
