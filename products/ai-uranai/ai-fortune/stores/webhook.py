"""STORES連携 — アップグレードコード管理"""
from __future__ import annotations

import hmac
import logging
import os
import secrets

from fastapi import APIRouter, Header, HTTPException, Request

from database.crud import AsyncSessionLocal, upgrade_user_plan

logger = logging.getLogger(__name__)
router = APIRouter()

# アップグレードコード管理（サーバー再起動でリセット。本番はDBまたはRedisへ移行する）
_upgrade_codes: dict[str, dict] = {}


def generate_upgrade_code(line_user_id: str, plan: str) -> str:
    """アップグレードコードを生成する（管理エンドポイントから呼ぶ）"""
    prefix = os.environ.get("UPGRADE_CODE_PREFIX", "SION")
    code = f"{prefix}-{secrets.token_hex(4).upper()}"
    _upgrade_codes[code] = {"line_user_id": line_user_id, "plan": plan, "used": False}
    logger.info(f"コード生成: {code} → {line_user_id} ({plan})")
    return code


async def handle_upgrade_code(line_user_id: str, code: str) -> str:
    """
    LINEでコードを受け取った時の処理。
    プランをアップグレードして確認メッセージを返す。
    """
    normalized = code.strip().upper()
    entry = _upgrade_codes.get(normalized)

    if entry is None:
        return "コードが見つかりません。正しいコードをご確認ください🙏"

    if entry["used"]:
        return "このコードはすでに使用済みです。ご不明な点はお問い合わせください。"

    async with AsyncSessionLocal() as session:
        await upgrade_user_plan(session, line_user_id, entry["plan"])

    entry["used"] = True

    plan_label = {
        "lite": "ライトプラン（¥480/月）",
        "standard": "スタンダードプラン（¥980/月）",
    }.get(entry["plan"], entry["plan"])

    extra = (
        "\n毎朝7時からパーソナル運勢をお届けします☀️"
        if entry["plan"] == "standard"
        else ""
    )

    return (
        f"✨ {plan_label}へのアップグレード完了！\n\n"
        f"これから占いをお楽しみください🌟{extra}"
    )


@router.post("/admin/generate-code")
async def generate_code_endpoint(
    request: Request,
    x_admin_key: str = Header(alias="X-Admin-Key"),
) -> dict:
    """
    管理者向け: アップグレードコード生成エンドポイント。
    X-Admin-Key ヘッダーで認証する。
    Request body: {"line_user_id": "Uxxxx", "plan": "lite" | "standard"}
    """
    admin_key = os.environ.get("ADMIN_SECRET_KEY", "")
    if not admin_key or not hmac.compare_digest(x_admin_key, admin_key):
        raise HTTPException(status_code=403, detail="Forbidden")

    body = await request.json()
    line_user_id: str = body.get("line_user_id", "")
    plan: str = body.get("plan", "lite")

    if not line_user_id:
        raise HTTPException(status_code=400, detail="line_user_id is required")
    if plan not in ("lite", "standard"):
        raise HTTPException(status_code=400, detail="plan must be 'lite' or 'standard'")

    code = generate_upgrade_code(line_user_id, plan)
    return {"code": code, "line_user_id": line_user_id, "plan": plan}


@router.post("/admin/upgrade-user")
async def upgrade_user_endpoint(
    request: Request,
    x_admin_key: str = Header(alias="X-Admin-Key"),
) -> dict:
    """
    管理者向け: 直接プランアップグレードエンドポイント。
    Request body: {"line_user_id": "Uxxxx", "plan": "lite" | "standard"}
    """
    admin_key = os.environ.get("ADMIN_SECRET_KEY", "")
    if not admin_key or not hmac.compare_digest(x_admin_key, admin_key):
        raise HTTPException(status_code=403, detail="Forbidden")

    body = await request.json()
    line_user_id: str = body.get("line_user_id", "")
    plan: str = body.get("plan", "lite")

    if not line_user_id:
        raise HTTPException(status_code=400, detail="line_user_id is required")
    if plan not in ("lite", "standard", "free"):
        raise HTTPException(status_code=400, detail="Invalid plan")

    async with AsyncSessionLocal() as session:
        user = await upgrade_user_plan(session, line_user_id, plan)

    return {"status": "upgraded", "line_user_id": line_user_id, "plan": user.plan}
