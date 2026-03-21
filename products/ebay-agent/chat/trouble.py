"""トラブル管理 — リターン/キャンセル/ディスプート"""
from __future__ import annotations

import logging
from typing import List

from sqlalchemy.orm import Session

from ebay_core.client import (
    get_return_requests,
    get_return_detail,
    get_cancellation_requests,
    respond_to_cancellation,
)

logger = logging.getLogger(__name__)

# ステータス日本語マッピング
RETURN_STATUS_JA = {
    "RETURN_REQUESTED": "リターンリクエスト",
    "WAITING_FOR_SELLER_RESPONSE": "対応待ち",
    "SELLER_RESPONSE_PAST_DUE": "対応期限超過",
    "WAITING_FOR_RETURN_SHIPMENT": "バイヤー返送待ち",
    "RETURN_SHIPPED": "返送済み",
    "DELIVERED": "返品到着",
    "REFUND_ISSUED": "返金完了",
    "CLOSED": "クローズ",
    "ESCALATED": "エスカレート",
}

CANCEL_STATUS_JA = {
    "CANCEL_REQUESTED": "キャンセルリクエスト",
    "CANCEL_PENDING": "キャンセル待ち",
    "CANCEL_ACCEPTED": "キャンセル承認",
    "CANCEL_DECLINED": "キャンセル拒否",
    "CANCEL_CLOSED": "クローズ",
}

TROUBLE_ICONS = {
    "RETURN_REQUESTED": "↩️",
    "WAITING_FOR_SELLER_RESPONSE": "⏰",
    "SELLER_RESPONSE_PAST_DUE": "🚨",
    "WAITING_FOR_RETURN_SHIPMENT": "📦",
    "RETURN_SHIPPED": "🚚",
    "DELIVERED": "✅",
    "REFUND_ISSUED": "💰",
    "ESCALATED": "⚠️",
    "CANCEL_REQUESTED": "❌",
    "CANCEL_PENDING": "⏳",
}


def get_troubles_for_buyer(buyer_username: str) -> dict:
    """バイヤーに関連するトラブル一覧を取得する。"""
    returns = get_return_requests()
    cancels = get_cancellation_requests()

    buyer_returns = [r for r in returns if r.get("buyer") == buyer_username]
    buyer_cancels = [c for c in cancels if c.get("buyer") == buyer_username]

    return {
        "returns": [_enrich_return(r) for r in buyer_returns],
        "cancellations": [_enrich_cancel(c) for c in buyer_cancels],
        "total_troubles": len(buyer_returns) + len(buyer_cancels),
        "has_active_trouble": any(
            r.get("status") not in ("CLOSED", "REFUND_ISSUED") for r in buyer_returns
        ) or any(
            c.get("status") not in ("CANCEL_CLOSED", "CANCEL_ACCEPTED", "CANCEL_DECLINED")
            for c in buyer_cancels
        ),
    }


def get_troubles_for_order(order_id: str) -> dict:
    """特定注文のトラブル状態を取得する。"""
    returns = get_return_requests(order_id=order_id)
    cancels = get_cancellation_requests(order_id=order_id)

    return {
        "returns": [_enrich_return(r) for r in returns],
        "cancellations": [_enrich_cancel(c) for c in cancels],
        "has_trouble": len(returns) > 0 or len(cancels) > 0,
    }


def accept_cancel(cancel_id: str) -> dict:
    """キャンセルリクエストを承認する。"""
    return respond_to_cancellation(cancel_id, accept=True)


def decline_cancel(cancel_id: str) -> dict:
    """キャンセルリクエストを拒否する。"""
    return respond_to_cancellation(cancel_id, accept=False)


def _enrich_return(r: dict) -> dict:
    """リターンデータに日本語ステータスとアイコンを追加する。"""
    status = r.get("status", "")
    r["status_ja"] = RETURN_STATUS_JA.get(status, status)
    r["icon"] = TROUBLE_ICONS.get(status, "📋")
    r["is_urgent"] = status in (
        "WAITING_FOR_SELLER_RESPONSE",
        "SELLER_RESPONSE_PAST_DUE",
        "ESCALATED",
    )
    return r


def _enrich_cancel(c: dict) -> dict:
    """キャンセルデータに日本語ステータスとアイコンを追加する。"""
    status = c.get("status", "")
    c["status_ja"] = CANCEL_STATUS_JA.get(status, status)
    c["icon"] = TROUBLE_ICONS.get(status, "📋")
    c["is_urgent"] = status in ("CANCEL_REQUESTED", "CANCEL_PENDING")
    return c
