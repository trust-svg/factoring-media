"""eBay Platform Notifications — Webhook受信ハンドラー

eBayからのイベント通知を受信し、自動メッセージエンジンに渡す。

対応イベント:
- FeedbackReceived: フィードバック受領
- FixedPriceTransaction: 購入完了
- ItemMarkedShipped: 発送完了
- BestOfferDeclined: オファー拒否
- MyMessagesM2MMessage: 新着バイヤーメッセージ
- ReturnCreated: リターンリクエスト
- BuyerCancelRequested: キャンセルリクエスト
"""
from __future__ import annotations

import hashlib
import json
import logging
import xml.etree.ElementTree as ET
from typing import Dict, Optional

from database.models import get_db

logger = logging.getLogger(__name__)


# ── Webhook検証 ──────────────────────────────────────────

def verify_challenge(challenge_code: str, verification_token: str, endpoint_url: str) -> str:
    """eBay Webhook検証チャレンジに応答する。

    SHA256(challengeCode + verificationToken + endpointUrl)
    """
    raw = challenge_code + verification_token + endpoint_url
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ── イベントパーサー ─────────────────────────────────────

def parse_notification(body: str) -> Optional[Dict]:
    """eBay Platform Notification XMLをパースする。

    Returns:
        {
            "event_type": str,
            "buyer_username": str,
            "item_id": str,
            "order_id": str,
            "data": dict,  # イベント固有データ
        }
    """
    try:
        # JSON形式の場合（新しいeBay Notification API）
        if body.strip().startswith("{"):
            return _parse_json_notification(body)

        # XML形式の場合（従来のPlatform Notifications）
        return _parse_xml_notification(body)
    except Exception as e:
        logger.error(f"通知パースエラー: {e}")
        return None


def _parse_json_notification(body: str) -> Optional[Dict]:
    """JSON形式のeBay通知をパースする。"""
    payload = json.loads(body)

    # Marketplace Account Deletion通知（GDPRコンプライアンス）
    if "metadata" in payload and "topic" in payload.get("metadata", {}):
        topic = payload["metadata"]["topic"]
        logger.info(f"eBay通知受信 (JSON topic): {topic}")

    notification_type = payload.get("NotificationEventName", "")
    if not notification_type:
        notification_type = payload.get("topic", payload.get("eventType", ""))

    event_map = {
        "FeedbackReceived": "feedback_received",
        "FixedPriceTransaction": "fixed_price_transaction",
        "ItemMarkedShipped": "item_shipped",
        "BestOfferDeclined": "best_offer_declined",
        "BestOffer": "best_offer_declined",
        "MyMessagesM2MMessage": "new_message",
        "ReturnCreated": "return_created",
        "BuyerCancelRequested": "cancel_requested",
    }
    event_type = event_map.get(notification_type, notification_type)

    return {
        "event_type": event_type,
        "buyer_username": payload.get("BuyerUserID", payload.get("buyerUsername", "")),
        "item_id": payload.get("ItemID", payload.get("itemId", "")),
        "order_id": payload.get("OrderID", payload.get("orderId", "")),
        "data": payload,
    }


def _parse_xml_notification(body: str) -> Optional[Dict]:
    """XML形式のeBay Platform Notificationをパースする。"""
    ns = {"soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
          "e": "urn:ebay:apis:eBLBaseComponents"}

    root = ET.fromstring(body)

    # SOAP Envelope の中身を取得
    soap_body = root.find(".//soapenv:Body", ns)
    if soap_body is None:
        # 非SOAPの場合
        soap_body = root

    # イベントタイプ判定
    notification_type = ""
    for child in soap_body:
        tag = child.tag
        if "}" in tag:
            tag = tag.split("}")[-1]
        if "Response" in tag or "Notification" in tag:
            notification_type = tag.replace("Response", "").replace("Notification", "")
            break

    # NotificationEventName要素から取得
    event_name_el = root.find(".//e:NotificationEventName", ns)
    if event_name_el is not None and event_name_el.text:
        notification_type = event_name_el.text

    event_map = {
        "FeedbackReceived": "feedback_received",
        "Feedback": "feedback_received",
        "FixedPriceTransaction": "fixed_price_transaction",
        "ItemMarkedShipped": "item_shipped",
        "BestOfferDeclined": "best_offer_declined",
        "BestOffer": "best_offer_declined",
        "MyMessagesM2MMessage": "new_message",
        "ReturnCreated": "return_created",
        "BuyerCancelRequested": "cancel_requested",
    }
    event_type = event_map.get(notification_type, notification_type)

    # 共通フィールド抽出
    buyer = (
        _find_text(root, ".//e:BuyerUserID", ns)
        or _find_text(root, ".//e:Sender", ns)
        or _find_text(root, ".//e:UserID", ns)
        or ""
    )
    item_id = _find_text(root, ".//e:ItemID", ns) or ""
    order_id = (
        _find_text(root, ".//e:OrderID", ns)
        or _find_text(root, ".//e:ExtendedOrderID", ns)
        or ""
    )

    # イベント固有データ
    extra_data = {}

    if event_type == "feedback_received":
        extra_data["comment_text"] = _find_text(root, ".//e:CommentText", ns) or ""
        extra_data["comment_type"] = _find_text(root, ".//e:CommentType", ns) or ""
        extra_data["feedback_score"] = _find_text(root, ".//e:FeedbackScore", ns) or ""

    elif event_type == "fixed_price_transaction":
        extra_data["transaction_price"] = _find_text(root, ".//e:TransactionPrice", ns) or ""
        extra_data["quantity_purchased"] = _find_text(root, ".//e:QuantityPurchased", ns) or ""
        extra_data["item_title"] = _find_text(root, ".//e:Title", ns) or ""

    elif event_type == "item_shipped":
        extra_data["tracking_number"] = _find_text(root, ".//e:ShipmentTrackingNumber", ns) or ""
        extra_data["carrier"] = _find_text(root, ".//e:ShippingCarrierUsed", ns) or ""

    elif event_type == "best_offer_declined":
        extra_data["offer_price"] = _find_text(root, ".//e:Price", ns) or ""
        extra_data["buyer_message"] = _find_text(root, ".//e:BuyerMessage", ns) or ""

    logger.info(f"eBay通知パース完了: {event_type} buyer={buyer} item={item_id}")

    return {
        "event_type": event_type,
        "buyer_username": buyer,
        "item_id": item_id,
        "order_id": order_id,
        "data": extra_data,
    }


def _find_text(root, path: str, ns: dict) -> Optional[str]:
    """XMLからテキストを安全に取得する。"""
    el = root.find(path, ns)
    return el.text if el is not None else None


# ── イベントハンドラー ───────────────────────────────────

async def handle_notification(body: str) -> Dict:
    """受信した通知を処理し、必要に応じて自動メッセージを送信する。"""
    parsed = parse_notification(body)
    if not parsed:
        return {"status": "parse_error"}

    event_type = parsed["event_type"]
    buyer = parsed["buyer_username"]
    item_id = parsed["item_id"]
    order_id = parsed["order_id"]
    data = parsed.get("data", {})

    logger.info(f"Webhook処理: {event_type} buyer={buyer} item={item_id}")

    # 自動メッセージ対象のイベントタイプ
    auto_message_events = {
        "feedback_received",
        "fixed_price_transaction",
        "item_shipped",
        "best_offer_declined",
    }

    result = {"status": "received", "event_type": event_type}

    if event_type in auto_message_events and buyer:
        from chat.auto_message import process_event
        db = get_db()
        try:
            auto_result = await process_event(
                db=db,
                event_type=event_type,
                buyer_username=buyer,
                item_id=item_id,
                order_id=order_id,
                event_data=data,
            )
            result["auto_message"] = auto_result
        except Exception as e:
            logger.error(f"自動メッセージ処理エラー: {e}")
            result["auto_message_error"] = str(e)
        finally:
            db.close()

    elif event_type == "new_message":
        # 新着メッセージ → 同期トリガー + Telegram通知
        result["action"] = "sync_triggered"
        try:
            _notify_new_message(buyer, item_id)
        except Exception as e:
            logger.warning(f"通知エラー: {e}")

    return result


def _notify_new_message(buyer: str, item_id: str):
    """新着メッセージをTelegramに通知する。"""
    try:
        import requests
        import os
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "323107833")

        if not bot_token:
            return

        text = f"📩 New eBay message from {buyer}"
        if item_id:
            text += f"\nItem: {item_id}"
        text += "\n→ /chat で確認"

        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        logger.warning(f"Telegram通知エラー: {e}")
