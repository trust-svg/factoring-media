"""自動メッセージエンジン — イベント駆動のメッセージ自動送信"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy.orm import Session

from database.models import (
    AutoMessageLog,
    AutoMessageRule,
    BuyerExclude,
    BuyerMessage,
    MessageTemplate,
    SalesRecord,
)
from chat.variables import resolve_variables
from ebay_core.client import send_buyer_message

logger = logging.getLogger(__name__)


# ── リピーター判定 ───────────────────────────────────────

def is_repeat_buyer(db: Session, buyer_username: str) -> bool:
    """バイヤーが過去に2回以上購入しているか判定する。"""
    count = db.query(SalesRecord).filter(
        SalesRecord.buyer_name == buyer_username
    ).count()
    return count > 1


# ── イベント処理 ─────────────────────────────────────────

async def process_event(
    db: Session,
    event_type: str,
    buyer_username: str,
    item_id: str = "",
    order_id: str = "",
    event_data: Optional[Dict] = None,
) -> Dict:
    """eBayイベントを受けて自動メッセージを処理する。

    Args:
        db: DBセッション
        event_type: イベントタイプ
            - feedback_received: フィードバック受領
            - fixed_price_transaction: 購入完了
            - item_shipped: 発送完了
            - best_offer_declined: オファー拒否
        buyer_username: バイヤーのユーザー名
        item_id: eBay Item ID
        order_id: eBay Order ID
        event_data: イベント追加データ

    Returns:
        {"sent": bool, "reason": str, "message_body": str}
    """
    data = event_data or {}

    # 1. アクティブなルールを検索
    rule = db.query(AutoMessageRule).filter(
        AutoMessageRule.event_type == event_type,
        AutoMessageRule.is_active == 1,
    ).first()

    if not rule:
        return {"sent": False, "reason": f"No active rule for {event_type}"}

    # 2. 除外リストチェック
    excluded = db.query(BuyerExclude).filter(
        BuyerExclude.buyer_username == buyer_username
    ).first()

    if excluded:
        logger.info(f"自動メッセージスキップ（除外バイヤー）: {buyer_username}")
        return {"sent": False, "reason": f"Buyer excluded: {excluded.reason or 'blocklist'}"}

    # 3. リピーター判定
    repeat = is_repeat_buyer(db, buyer_username)

    # 4. テンプレート選択
    template_id = rule.template_id
    if repeat and rule.repeat_buyer_template_id:
        template_id = rule.repeat_buyer_template_id

    template = db.query(MessageTemplate).filter(
        MessageTemplate.id == template_id,
        MessageTemplate.is_active == 1,
    ).first()

    if not template:
        return {"sent": False, "reason": f"Template {template_id} not found or inactive"}

    # 5. 変数展開
    message_body = resolve_variables(
        template.body_en,
        db=db,
        buyer_username=buyer_username,
        item_id=item_id,
        order_id=order_id,
        event_data=data,
    )

    if not message_body.strip():
        return {"sent": False, "reason": "Empty message after variable resolution"}

    # 6. 送信
    # item_id が必要（eBay API要件）
    send_item_id = item_id or data.get("item_id", "")
    if not send_item_id:
        # SalesRecord からitem_idを取得
        if order_id:
            sale = db.query(SalesRecord).filter(SalesRecord.order_id == order_id).first()
            if sale:
                send_item_id = sale.item_id

    if not send_item_id:
        return {"sent": False, "reason": "No item_id available for sending"}

    result = send_buyer_message(
        item_id=send_item_id,
        recipient_id=buyer_username,
        body=message_body,
    )

    # 7. ログ記録
    log_entry = AutoMessageLog(
        rule_id=rule.id,
        event_type=event_type,
        buyer_username=buyer_username,
        item_id=send_item_id,
        order_id=order_id,
        message_body=message_body,
        is_repeat_buyer=1 if repeat else 0,
        success=1 if result.get("success") else 0,
        error_message=result.get("error"),
    )
    db.add(log_entry)

    # 送信カウント更新
    if result.get("success"):
        rule.send_count += 1
        rule.last_sent_at = datetime.utcnow()

        # BuyerMessage にも保存
        outbound = BuyerMessage(
            ebay_message_id=f"auto_{datetime.utcnow().timestamp()}",
            item_id=send_item_id,
            sender="me",
            recipient=buyer_username,
            direction="outbound",
            subject=f"[Auto] {rule.name}",
            body=message_body,
            is_read=1,
            responded=1,
            received_at=datetime.utcnow(),
            synced_at=datetime.utcnow(),
        )
        db.add(outbound)

    db.commit()

    status = "sent" if result.get("success") else "failed"
    logger.info(
        f"自動メッセージ {status}: {event_type} → {buyer_username} "
        f"(repeat={repeat}, rule={rule.name})"
    )

    return {
        "sent": result.get("success", False),
        "reason": result.get("error", "OK"),
        "message_body": message_body,
        "is_repeat_buyer": repeat,
        "template_id": template_id,
        "rule_name": rule.name,
    }


# ── ルール管理 ───────────────────────────────────────────

def get_rules(db: Session) -> list:
    """全自動メッセージルールを取得する。"""
    rules = db.query(AutoMessageRule).order_by(AutoMessageRule.event_type).all()
    result = []
    for r in rules:
        # テンプレート名を取得
        tmpl = db.query(MessageTemplate).filter(MessageTemplate.id == r.template_id).first()
        repeat_tmpl = None
        if r.repeat_buyer_template_id:
            repeat_tmpl = db.query(MessageTemplate).filter(
                MessageTemplate.id == r.repeat_buyer_template_id
            ).first()

        result.append({
            "id": r.id,
            "event_type": r.event_type,
            "name": r.name,
            "template_id": r.template_id,
            "template_name": tmpl.title if tmpl else "",
            "repeat_buyer_template_id": r.repeat_buyer_template_id,
            "repeat_buyer_template_name": repeat_tmpl.title if repeat_tmpl else "",
            "is_active": bool(r.is_active),
            "delay_minutes": r.delay_minutes,
            "send_count": r.send_count,
            "last_sent_at": r.last_sent_at.isoformat() if r.last_sent_at else "",
        })
    return result


def save_rule(db: Session, data: dict) -> dict:
    """ルールを作成/更新する。"""
    rule_id = data.get("id")
    if rule_id:
        rule = db.query(AutoMessageRule).filter(AutoMessageRule.id == rule_id).first()
        if not rule:
            return {"error": "Rule not found"}
    else:
        rule = AutoMessageRule()
        db.add(rule)

    rule.event_type = data.get("event_type", rule.event_type)
    rule.name = data.get("name", rule.name)
    rule.template_id = data.get("template_id", rule.template_id)
    rule.repeat_buyer_template_id = data.get("repeat_buyer_template_id")
    rule.is_active = data.get("is_active", 1)
    rule.delay_minutes = data.get("delay_minutes", 0)
    rule.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(rule)

    return {"success": True, "id": rule.id}


def toggle_rule(db: Session, rule_id: int) -> dict:
    """ルールのON/OFFを切り替える。"""
    rule = db.query(AutoMessageRule).filter(AutoMessageRule.id == rule_id).first()
    if not rule:
        return {"error": "Rule not found"}
    rule.is_active = 0 if rule.is_active else 1
    db.commit()
    return {"success": True, "is_active": bool(rule.is_active)}


def delete_rule(db: Session, rule_id: int) -> dict:
    """ルールを削除する。"""
    rule = db.query(AutoMessageRule).filter(AutoMessageRule.id == rule_id).first()
    if not rule:
        return {"error": "Rule not found"}
    db.delete(rule)
    db.commit()
    return {"success": True}


# ── 除外リスト管理 ───────────────────────────────────────

def get_exclude_list(db: Session) -> list:
    """除外バイヤー一覧を取得する。"""
    excludes = db.query(BuyerExclude).order_by(BuyerExclude.created_at.desc()).all()
    return [
        {
            "id": e.id,
            "buyer_username": e.buyer_username,
            "reason": e.reason or "",
            "created_at": e.created_at.isoformat() if e.created_at else "",
        }
        for e in excludes
    ]


def add_exclude(db: Session, buyer_username: str, reason: str = "") -> dict:
    """バイヤーを除外リストに追加する。"""
    existing = db.query(BuyerExclude).filter(
        BuyerExclude.buyer_username == buyer_username
    ).first()
    if existing:
        return {"error": "Already excluded"}

    exclude = BuyerExclude(buyer_username=buyer_username, reason=reason)
    db.add(exclude)
    db.commit()
    return {"success": True, "id": exclude.id}


def remove_exclude(db: Session, exclude_id: int) -> dict:
    """除外リストからバイヤーを削除する。"""
    exclude = db.query(BuyerExclude).filter(BuyerExclude.id == exclude_id).first()
    if not exclude:
        return {"error": "Not found"}
    db.delete(exclude)
    db.commit()
    return {"success": True}


# ── ログ取得 ─────────────────────────────────────────────

def get_auto_message_logs(db: Session, limit: int = 50) -> list:
    """自動メッセージ送信ログを取得する。"""
    logs = db.query(AutoMessageLog).order_by(
        AutoMessageLog.sent_at.desc()
    ).limit(limit).all()
    return [
        {
            "id": l.id,
            "rule_id": l.rule_id,
            "event_type": l.event_type,
            "buyer_username": l.buyer_username,
            "item_id": l.item_id,
            "order_id": l.order_id,
            "message_body": l.message_body[:100],
            "is_repeat_buyer": bool(l.is_repeat_buyer),
            "success": bool(l.success),
            "error_message": l.error_message or "",
            "sent_at": l.sent_at.isoformat() if l.sent_at else "",
        }
        for l in logs
    ]
