"""自動メッセージエンジン — イベント駆動のメッセージ自動送信"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Optional

from sqlalchemy.orm import Session

from database.models import (
    AutoMessageLog,
    AutoMessageRule,
    BuyerExclude,
    BuyerMessage,
    MessageTemplate,
    NoReplyCandidateSkip,
    SalesRecord,
)
from chat.variables import resolve_variables
from ebay_core.client import send_buyer_message

logger = logging.getLogger(__name__)

# 未返信自動返信フィルタ設定（D フィルタ）
NO_REPLY_LOOKBACK_DAYS = 14           # 過去X日以内のメッセージのみ対象
NO_REPLY_MIN_TEXT_LENGTH = 15         # 絵文字/記号除去後の最小文字数
NO_REPLY_URL_PATTERN = r"https?://"   # URL含有メッセージは除外


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


# ── 未返信タイムアウト自動返信 ──────────────────────────────

def _passes_d_filter(body: str) -> bool:
    """D フィルタ: 質問っぽいメッセージのみ true。

    - 絵文字/記号除去後 15文字以上
    - 質問符 "?" または "？" を含む
    - URL（http(s)://）を含まない（URL中の ? を誤判定しない）
    """
    if not body:
        return False
    if re.search(NO_REPLY_URL_PATTERN, body):
        return False
    text = re.sub(r"[^\w\s?.!a-zA-Z]", "", body).strip()
    if len(text) < NO_REPLY_MIN_TEXT_LENGTH:
        return False
    return ("?" in body) or ("\uff1f" in body)


def get_no_reply_candidates(db: Session) -> list[dict]:
    """Dフィルタで未返信自動返信の候補を抽出する（送信はしない）。

    フィルタ条件:
    - event_type="no_reply_timeout" のアクティブルールが存在
    - inbound / sender != eBay, me
    - responded = 0
    - received_at <= now - delay_minutes（タイムアウト済み）
    - received_at >= now - 14日（古すぎるものは除外）
    - item_id / ebay_message_id あり
    - 除外バイヤーでない
    - 過去に送信/スキップ履歴なし
    - 購入履歴なし（AAQ のみ対象）
    - D フィルタ（質問符 + 15文字以上 + URL除外）
    """
    rule = db.query(AutoMessageRule).filter(
        AutoMessageRule.event_type == "no_reply_timeout",
        AutoMessageRule.is_active == 1,
    ).first()

    if not rule or rule.delay_minutes <= 0:
        return []

    template = db.query(MessageTemplate).filter(
        MessageTemplate.id == rule.template_id,
        MessageTemplate.is_active == 1,
    ).first()
    if not template:
        return []

    repeat_template = None
    if rule.repeat_buyer_template_id:
        repeat_template = db.query(MessageTemplate).filter(
            MessageTemplate.id == rule.repeat_buyer_template_id,
            MessageTemplate.is_active == 1,
        ).first()

    cutoff = datetime.utcnow() - timedelta(minutes=rule.delay_minutes)
    lookback = datetime.utcnow() - timedelta(days=NO_REPLY_LOOKBACK_DAYS)

    unreplied = db.query(BuyerMessage).filter(
        BuyerMessage.direction == "inbound",
        BuyerMessage.sender != "eBay",
        BuyerMessage.sender != "me",
        BuyerMessage.responded == 0,
        BuyerMessage.received_at <= cutoff,
        BuyerMessage.received_at >= lookback,
        BuyerMessage.item_id != "",
        BuyerMessage.ebay_message_id != "",
        BuyerMessage.ebay_message_id.isnot(None),
    ).all()

    if not unreplied:
        return []

    attempted = {
        (l.buyer_username, l.item_id)
        for l in db.query(
            AutoMessageLog.item_id, AutoMessageLog.buyer_username
        ).filter(AutoMessageLog.event_type == "no_reply_timeout").all()
    }
    skipped = {
        (s.buyer_username, s.item_id)
        for s in db.query(
            NoReplyCandidateSkip.item_id, NoReplyCandidateSkip.buyer_username
        ).all()
    }
    excluded_users = {
        e.buyer_username for e in db.query(BuyerExclude.buyer_username).all()
    }

    candidates = []
    for msg in unreplied:
        if msg.sender in excluded_users:
            continue
        key = (msg.sender, msg.item_id)
        if key in attempted or key in skipped:
            continue
        # 購入履歴なし（AAQ のみ）
        if db.query(SalesRecord).filter(SalesRecord.buyer_name == msg.sender).first():
            continue
        if not _passes_d_filter(msg.body):
            continue

        repeat = is_repeat_buyer(db, msg.sender)
        tmpl = repeat_template if (repeat and repeat_template) else template
        message_body = resolve_variables(
            tmpl.body_en,
            db=db,
            buyer_username=msg.sender,
            item_id=msg.item_id,
            order_id=msg.order_id or "",
        )
        if not message_body.strip():
            continue

        candidates.append({
            "id": msg.id,
            "ebay_message_id": msg.ebay_message_id,
            "buyer_username": msg.sender,
            "item_id": msg.item_id,
            "order_id": msg.order_id or "",
            "subject": msg.subject or "",
            "original_body": msg.body or "",
            "received_at": msg.received_at.isoformat() if msg.received_at else "",
            "is_repeat_buyer": repeat,
            "message_body_to_send": message_body,
            "rule_id": rule.id,
            "rule_name": rule.name,
        })

    candidates.sort(key=lambda c: c["received_at"])
    return candidates


def send_no_reply_candidate(db: Session, buyer_message_id: int) -> dict:
    """承認された候補を1件送信する。"""
    msg = db.query(BuyerMessage).filter(BuyerMessage.id == buyer_message_id).first()
    if not msg:
        return {"success": False, "error": "Message not found"}

    rule = db.query(AutoMessageRule).filter(
        AutoMessageRule.event_type == "no_reply_timeout",
        AutoMessageRule.is_active == 1,
    ).first()
    if not rule:
        return {"success": False, "error": "No active rule"}

    template = db.query(MessageTemplate).filter(
        MessageTemplate.id == rule.template_id,
        MessageTemplate.is_active == 1,
    ).first()
    if not template:
        return {"success": False, "error": "Template not found"}

    repeat = is_repeat_buyer(db, msg.sender)
    repeat_template = None
    if repeat and rule.repeat_buyer_template_id:
        repeat_template = db.query(MessageTemplate).filter(
            MessageTemplate.id == rule.repeat_buyer_template_id,
            MessageTemplate.is_active == 1,
        ).first()
    tmpl = repeat_template or template

    message_body = resolve_variables(
        tmpl.body_en,
        db=db,
        buyer_username=msg.sender,
        item_id=msg.item_id,
        order_id=msg.order_id or "",
    )
    if not message_body.strip():
        return {"success": False, "error": "Empty message after variable resolution"}

    result = send_buyer_message(
        item_id=msg.item_id,
        recipient_id=msg.sender,
        body=message_body,
    )

    log_entry = AutoMessageLog(
        rule_id=rule.id,
        event_type="no_reply_timeout",
        buyer_username=msg.sender,
        item_id=msg.item_id,
        order_id=msg.order_id or "",
        message_body=message_body,
        is_repeat_buyer=1 if repeat else 0,
        success=1 if result.get("success") else 0,
        error_message=result.get("error"),
    )
    db.add(log_entry)

    # スキップログにも「sent」として記録 → 再抽出されない
    db.add(NoReplyCandidateSkip(
        buyer_message_id=msg.id,
        buyer_username=msg.sender,
        item_id=msg.item_id,
        action="sent",
    ))

    if result.get("success"):
        rule.send_count += 1
        rule.last_sent_at = datetime.utcnow()
        msg.responded = 1
        msg.replied_at = datetime.utcnow()
        db.add(BuyerMessage(
            ebay_message_id=f"auto_noreply_{datetime.utcnow().timestamp()}",
            item_id=msg.item_id,
            sender="me",
            recipient=msg.sender,
            direction="outbound",
            subject=f"[Auto] {rule.name}",
            body=message_body,
            is_read=1,
            responded=1,
            received_at=datetime.utcnow(),
            synced_at=datetime.utcnow(),
        ))

    db.commit()
    return {
        "success": result.get("success", False),
        "error": result.get("error"),
        "buyer": msg.sender,
    }


def skip_no_reply_candidate(
    db: Session, buyer_message_id: int, action: str = "skip"
) -> dict:
    """候補をスキップする（次回以降の抽出対象外にする）。

    action:
    - skip: スキップのみ（対象外マーク）
    - excluded: バイヤーを BuyerExclude に追加（今後全自動メッセ対象外）
    """
    msg = db.query(BuyerMessage).filter(BuyerMessage.id == buyer_message_id).first()
    if not msg:
        return {"success": False, "error": "Message not found"}

    db.add(NoReplyCandidateSkip(
        buyer_message_id=msg.id,
        buyer_username=msg.sender,
        item_id=msg.item_id,
        action=action,
    ))

    if action == "excluded":
        existing = db.query(BuyerExclude).filter(
            BuyerExclude.buyer_username == msg.sender
        ).first()
        if not existing:
            db.add(BuyerExclude(
                buyer_username=msg.sender,
                reason="Manually excluded from no-reply auto-reply",
            ))

    db.commit()
    return {"success": True, "action": action}


def check_no_reply_timeout(db: Session) -> list[dict]:
    """スケジューラから呼ばれる。mode=='auto' のルールのみ候補を即送信。

    manual モードの場合は候補を抽出するだけで送信しない。
    """
    rule = db.query(AutoMessageRule).filter(
        AutoMessageRule.event_type == "no_reply_timeout",
        AutoMessageRule.is_active == 1,
    ).first()
    if not rule:
        return []

    if rule.mode != "auto":
        # manual モードは自動送信しない（承認UIから送信される）
        return []

    candidates = get_no_reply_candidates(db)
    results = []
    for cand in candidates:
        res = send_no_reply_candidate(db, cand["id"])
        results.append({
            "buyer": cand["buyer_username"],
            "item_id": cand["item_id"],
            "sent": res.get("success"),
            "error": res.get("error"),
        })
        logger.info(
            f"未返信自動返信 {'送信' if res.get('success') else '失敗'}: "
            f"{cand['buyer_username']} (item={cand['item_id']})"
        )
    return results


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
            "message_body": tmpl.body_en if tmpl else "",
            "repeat_buyer_template_id": r.repeat_buyer_template_id,
            "repeat_buyer_template_name": repeat_tmpl.title if repeat_tmpl else "",
            "message_body_repeat": repeat_tmpl.body_en if repeat_tmpl else "",
            "is_active": bool(r.is_active),
            "delay_minutes": r.delay_minutes,
            "mode": getattr(r, "mode", "manual") or "manual",
            "send_count": r.send_count,
            "last_sent_at": r.last_sent_at.isoformat() if r.last_sent_at else "",
        })
    return result


def save_rule(db: Session, data: dict) -> dict:
    """ルールを作成/更新する。

    message_body / message_body_repeat が渡された場合、
    テンプレートを自動作成/更新する。
    """
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
    rule.is_active = data.get("is_active", 1)
    rule.delay_minutes = data.get("delay_minutes", 0)
    if data.get("mode") in ("manual", "auto"):
        rule.mode = data["mode"]

    # インラインメッセージ本文 → テンプレート自動管理
    message_body = data.get("message_body")
    if message_body is not None and message_body.strip():
        rule.template_id = _upsert_template(
            db, rule.template_id, rule.name, message_body
        )
    elif data.get("template_id"):
        rule.template_id = data["template_id"]

    message_body_repeat = data.get("message_body_repeat")
    if message_body_repeat is not None and message_body_repeat.strip():
        rule.repeat_buyer_template_id = _upsert_template(
            db, rule.repeat_buyer_template_id, f"{rule.name} (Repeat)", message_body_repeat
        )
    elif data.get("repeat_buyer_template_id"):
        rule.repeat_buyer_template_id = data["repeat_buyer_template_id"]

    rule.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(rule)

    return {"success": True, "id": rule.id}


def _upsert_template(db: Session, template_id: int | None, title: str, body: str) -> int:
    """テンプレートを作成/更新して ID を返す。"""
    tmpl = None
    if template_id:
        tmpl = db.query(MessageTemplate).filter(MessageTemplate.id == template_id).first()

    if tmpl:
        tmpl.body_en = body
        tmpl.title = title
        tmpl.updated_at = datetime.utcnow()
    else:
        tmpl = MessageTemplate(
            title=title,
            body_en=body,
            category="auto",
            is_active=1,
        )
        db.add(tmpl)
        db.flush()  # ID を確定

    return tmpl.id


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
