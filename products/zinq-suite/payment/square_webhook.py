"""ZINQ Suite — Square 決済連携

フロー:
1. ユーザーがLINE Botで「プランを見る」タップ
2. Botがline_user_idをmetadataに埋め込んだSquare Checkout URLを生成
3. ユーザーがSquareで決済
4. Square Webhookが来る → subscription.created → line_user_idでプランを更新
5. Botがユーザーに「プレミアム登録完了！」をpush送信
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from dataclasses import dataclass
from typing import Literal, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from database.crud import (
    AsyncSessionLocal,
    downgrade_user,
    get_user_by_square_subscription,
    upgrade_user,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payment", tags=["payment"])

Plan = Literal["standard", "premium"]


@dataclass
class SquareEvent:
    event_type: Literal["created", "canceled"]
    line_user_id: str
    plan: Plan
    subscription_id: str
    customer_id: str


def parse_subscription_event(
    payload: dict,
    standard_plan_id: str,
    premium_plan_id: str,
) -> Optional[SquareEvent]:
    """Square WebhookペイロードをSquareEventに変換する。無関係なイベントはNoneを返す。"""
    event_type_raw = payload.get("type", "")
    if event_type_raw not in ("subscription.created", "subscription.updated"):
        return None

    try:
        sub = payload["data"]["object"]["subscription"]
    except (KeyError, TypeError):
        return None

    status = sub.get("status", "")
    line_user_id = (sub.get("metadata") or {}).get("line_user_id", "")
    if not line_user_id:
        return None

    plan_variation_id = sub.get("plan_variation_id", "")
    if plan_variation_id == standard_plan_id:
        plan: Plan = "standard"
    elif plan_variation_id == premium_plan_id:
        plan = "premium"
    else:
        return None

    if status == "ACTIVE" and event_type_raw == "subscription.created":
        event_type = "created"
    elif status == "CANCELED":
        event_type = "canceled"
    else:
        return None

    return SquareEvent(
        event_type=event_type,
        line_user_id=line_user_id,
        plan=plan,
        subscription_id=sub.get("id", ""),
        customer_id=sub.get("customer_id", ""),
    )


def generate_checkout_url(line_user_id: str, plan: Plan) -> str:
    """Square Checkout URL を生成する（line_user_idをreferenceとして埋め込む）"""
    base_url = os.environ.get("APP_BASE_URL", "")
    return f"{base_url}/payment/checkout?plan={plan}&uid={line_user_id}"


# ===================== Webhook エンドポイント =====================

@router.post("/webhook/square")
async def square_webhook(
    request: Request,
    x_square_hmacsha256_signature: str = Header(alias="X-Square-Hmacsha256-Signature", default=""),
) -> dict:
    body = await request.body()

    # 署名検証
    sig_key = os.environ.get("SQUARE_WEBHOOK_SIGNATURE_KEY", "")
    if sig_key:
        expected = hmac.new(
            sig_key.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, x_square_hmacsha256_signature):
            raise HTTPException(status_code=400, detail="Invalid signature")

    payload = await request.json()
    standard_plan_id = os.environ.get("SQUARE_STANDARD_PLAN_ID", "")
    premium_plan_id = os.environ.get("SQUARE_PREMIUM_PLAN_ID", "")

    event = parse_subscription_event(payload, standard_plan_id, premium_plan_id)
    if event is None:
        return {"status": "ignored"}

    async with AsyncSessionLocal() as session:
        if event.event_type == "created":
            await upgrade_user(
                session,
                event.line_user_id,
                plan=event.plan,
                square_customer_id=event.customer_id,
                square_subscription_id=event.subscription_id,
            )
            logger.info(f"プランアップグレード: {event.line_user_id} → {event.plan}")
        elif event.event_type == "canceled":
            await downgrade_user(session, event.line_user_id)
            logger.info(f"プランキャンセル: {event.line_user_id}")

    return {"status": "ok"}


# ===================== Checkout リダイレクト =====================

@router.get("/checkout")
async def checkout_redirect(plan: str, uid: str) -> dict:
    """Square Checkout URLを動的生成してリダイレクト"""
    return {"plan": plan, "uid": uid, "message": "Square Checkout連携は別途設定が必要です"}
