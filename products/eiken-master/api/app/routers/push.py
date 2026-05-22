import json
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import (
    INTERNAL_TOKEN,
    VAPID_CLAIMS_EMAIL,
    VAPID_PRIVATE_KEY,
    VAPID_PUBLIC_KEY,
)
from app.db import get_db
from app.models.push_subscription import PushSubscription
from app.models.session import StudySession
from app.routers.auth import current_user
from app.models.user import User

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

router = APIRouter()


def _webpush_available() -> bool:
    try:
        import pywebpush  # noqa: F401

        return True
    except ImportError:
        return False


def _send_push(subscription: PushSubscription, payload: dict) -> None:
    from pywebpush import webpush, WebPushException

    subscription_info = {
        "endpoint": subscription.endpoint,
        "keys": {
            "p256dh": subscription.p256dh,
            "auth": subscription.auth,
        },
    }
    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": f"mailto:{VAPID_CLAIMS_EMAIL}"},
        )
    except WebPushException as e:
        logger.warning("WebPush failed for %s: %s", subscription.endpoint[:40], e)
        raise


class SubscribeRequest(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


@router.get("/vapid-public-key")
async def get_vapid_public_key():
    if not VAPID_PUBLIC_KEY:
        raise HTTPException(status_code=503, detail="Push notifications not configured")
    return {"public_key": VAPID_PUBLIC_KEY}


@router.post("/subscribe", status_code=201)
async def subscribe(
    body: SubscribeRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        raise HTTPException(status_code=503, detail="Push notifications not configured")
    existing = (
        db.query(PushSubscription)
        .filter_by(user_id=user.id, endpoint=body.endpoint)
        .first()
    )
    if existing:
        return {"id": existing.id}

    sub = PushSubscription(
        user_id=user.id,
        endpoint=body.endpoint,
        p256dh=body.p256dh,
        auth=body.auth,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return {"id": sub.id}


@router.delete("/unsubscribe")
async def unsubscribe(
    body: SubscribeRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    sub = (
        db.query(PushSubscription)
        .filter_by(user_id=user.id, endpoint=body.endpoint)
        .first()
    )
    if sub:
        db.delete(sub)
        db.commit()
    return {"ok": True}


@router.post("/test")
async def send_test(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not _webpush_available():
        raise HTTPException(status_code=503, detail="pywebpush not installed")
    subs = db.query(PushSubscription).filter_by(user_id=user.id).all()
    if not subs:
        raise HTTPException(status_code=404, detail="No subscriptions found")
    payload = {
        "title": "英検マスター",
        "body": "プッシュ通知のテストです！",
        "icon": "/icon-192.png",
    }
    sent = 0
    dead: list[PushSubscription] = []
    for sub in subs:
        try:
            _send_push(sub, payload)
            sent += 1
        except Exception:
            dead.append(sub)
    for sub in dead:
        db.delete(sub)
    if dead:
        db.commit()
    return {"sent": sent, "removed_stale": len(dead)}


@router.post("/send-reminders")
async def send_reminders(
    x_internal_token: str = Header(default="", alias="X-Internal-Token"),
    db: Session = Depends(get_db),
):
    """Called by VPS cron every hour. Requires X-Internal-Token header."""
    if INTERNAL_TOKEN and x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not _webpush_available() or not VAPID_PRIVATE_KEY:
        return {"skipped": True, "reason": "not configured"}

    now_jst = datetime.now(JST)
    current_hour = now_jst.hour
    current_weekday = now_jst.weekday()  # 0=Mon, 6=Sun

    subs_with_users = (
        db.query(PushSubscription, User)
        .join(User, PushSubscription.user_id == User.id)
        .all()
    )

    # Group subscriptions by user so multi-device users get ONE notification decision
    user_subs: dict[str, list[PushSubscription]] = {}
    user_map: dict[str, User] = {}
    for sub, user in subs_with_users:
        user_subs.setdefault(user.id, []).append(sub)
        user_map[user.id] = user

    today_start = now_jst.replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None
    )
    sent = 0
    dead: list[PushSubscription] = []

    for user_id, subs in user_subs.items():
        user = user_map[user_id]

        # reminder_schedule takes priority: {"0": "19:00", "2": "21:00", ...}
        schedule = None
        if user.reminder_schedule:
            try:
                schedule = json.loads(user.reminder_schedule)
            except (json.JSONDecodeError, TypeError):
                schedule = None

        if schedule is not None:
            # New per-day schedule mode
            time_for_today = schedule.get(str(current_weekday))
            if not time_for_today:
                continue  # this day not in schedule
            try:
                h = int(time_for_today.split(":")[0])
            except (ValueError, AttributeError):
                continue
            if h != current_hour:
                continue
        else:
            # Legacy mode: single reminder_time + reminder_days
            try:
                h = int((user.reminder_time or "20:00").split(":")[0])
            except (ValueError, AttributeError):
                h = 20
            if h != current_hour:
                continue
            try:
                days = json.loads(user.reminder_days or "[0,1,2,3,4,5,6]")
            except (json.JSONDecodeError, TypeError):
                days = list(range(7))
            if current_weekday not in days:
                continue

        # Skip if already studied today
        studied_today = (
            db.query(StudySession)
            .filter(
                StudySession.user_id == user_id,
                StudySession.started_at >= today_start,
            )
            .first()
        )
        if studied_today:
            continue

        payload = {
            "title": "英検マスター",
            "body": f"今日の学習、まだですか？ 残り{_hours_left(now_jst)}時間で一日が終わります。",
            "icon": "/icon-192.png",
            "url": "/",
        }
        # Send to ALL devices of this user at once; count as 1 user notified
        user_sent = False
        for sub in subs:
            try:
                _send_push(sub, payload)
                user_sent = True
            except Exception:
                dead.append(sub)
        if user_sent:
            sent += 1

    for sub in dead:
        db.delete(sub)
    if dead:
        db.commit()
    return {"sent": sent, "removed_stale": len(dead)}


@router.post("/send-completion")
async def send_completion(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Called by frontend when the user finishes all daily tasks."""
    if not _webpush_available() or not VAPID_PRIVATE_KEY:
        return {"skipped": True, "reason": "not configured"}
    subs = db.query(PushSubscription).filter_by(user_id=user.id).all()
    if not subs:
        return {"sent": 0}
    payload = {
        "title": "🎉 今日の学習、完了！",
        "body": "ホーホー！全タスク達成だよ！フクロウ博士もとっても誇りに思ってるよ！",
        "icon": "/icon-192.png",
        "url": "/home",
    }
    sent = 0
    dead: list[PushSubscription] = []
    for sub in subs:
        try:
            _send_push(sub, payload)
            sent += 1
        except Exception:
            dead.append(sub)
    for sub in dead:
        db.delete(sub)
    if dead:
        db.commit()
    return {"sent": sent, "removed_stale": len(dead)}


def _hours_left(now: datetime) -> int:
    tomorrow = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(0, int((tomorrow - now).total_seconds() // 3600))
