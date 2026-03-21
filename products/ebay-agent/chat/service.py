"""チャットビジネスロジック — sync, draft, send"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

import anthropic
from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import BuyerMessage, Listing, MessageTemplate, SalesRecord
from ebay_core.client import get_buyer_messages, send_buyer_message, mark_messages_read
from chat.translation import translate_to_ja, translate_to_en

logger = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def _get_anthropic() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


# ── メッセージ同期 ───────────────────────────────────────

async def sync_messages(db: Session, days: int = 7) -> dict:
    """eBay APIからメッセージを取得してDBに同期する。"""
    raw_messages = get_buyer_messages(days=days, limit=50)
    new_count = 0
    updated_count = 0

    for msg in raw_messages:
        ebay_id = msg["message_id"]
        if not ebay_id:
            continue

        existing = db.query(BuyerMessage).filter(
            BuyerMessage.ebay_message_id == ebay_id
        ).first()

        if existing:
            # 既読/返信済みステータスの更新
            changed = False
            if msg["is_read"] and not existing.is_read:
                existing.is_read = 1
                changed = True
            if msg["responded"] and not existing.responded:
                existing.responded = 1
                changed = True
            if changed:
                existing.synced_at = datetime.utcnow()
                updated_count += 1
        else:
            # 新規メッセージ → 自動翻訳
            body = msg.get("body", "")
            translated = ""
            try:
                translated = await translate_to_ja(body)
            except Exception as e:
                logger.warning(f"翻訳スキップ: {e}")

            # センチメント分析
            sentiment_data = {"sentiment": "", "urgency": "", "note": ""}
            try:
                from chat.intelligence import analyze_sentiment
                sentiment_data = await analyze_sentiment(body)
            except Exception as e:
                logger.warning(f"センチメント分析スキップ: {e}")

            new_msg = BuyerMessage(
                ebay_message_id=ebay_id,
                item_id=msg.get("item_id", ""),
                sender=msg.get("sender", ""),
                recipient="me",
                direction="inbound",
                subject=msg.get("subject", ""),
                body=body,
                body_translated=translated,
                is_read=1 if msg["is_read"] else 0,
                responded=1 if msg["responded"] else 0,
                sentiment=sentiment_data.get("sentiment", ""),
                urgency=sentiment_data.get("urgency", ""),
                sentiment_note=sentiment_data.get("note", ""),
                received_at=_parse_date(msg.get("received_date", "")),
                synced_at=datetime.utcnow(),
            )
            db.add(new_msg)
            new_count += 1

    db.commit()
    logger.info(f"メッセージ同期完了: 新規{new_count}件, 更新{updated_count}件")
    return {"new": new_count, "updated": updated_count, "total_fetched": len(raw_messages)}


# ── 会話一覧 ─────────────────────────────────────────────

def get_conversations(
    db: Session,
    status: str = "all",
    search: str = "",
    limit: int = 50,
) -> list[dict]:
    """会話一覧を取得する（商品ベース → バイヤーリスト構造）。

    Returns: {
        "items": [{item_id, title, thumbnail, unread_count, buyers: [{buyer, last_message, ...}]}],
        "conversations": [{buyer, item_id, ...}]  # 従来互換
    }
    """
    # eBayシステムメッセージを除外（sender=eBay）
    query = db.query(BuyerMessage).filter(
        BuyerMessage.direction == "inbound",
        BuyerMessage.sender != "eBay",
    )

    if status == "unread":
        query = query.filter(BuyerMessage.is_read == 0)
    elif status == "read":
        query = query.filter(BuyerMessage.is_read == 1)

    if search:
        like_term = f"%{search}%"
        query = query.filter(
            (BuyerMessage.sender.ilike(like_term))
            | (BuyerMessage.subject.ilike(like_term))
            | (BuyerMessage.body.ilike(like_term))
            | (BuyerMessage.item_id.ilike(like_term))
        )

    messages = query.order_by(BuyerMessage.received_at.desc()).all()

    # 商品 → バイヤーリスト構造を構築
    item_map: dict[str, dict] = {}
    conv_map: dict[str, dict] = {}

    for msg in messages:
        iid = msg.item_id or "_no_item"

        # 商品情報
        if iid not in item_map:
            thumbnail = ""
            item_title = ""
            if iid != "_no_item":
                listing = db.query(Listing).filter(Listing.listing_id == iid).first()
                if listing:
                    import json as _json
                    try:
                        imgs = _json.loads(listing.image_urls_json) if listing.image_urls_json else []
                        thumbnail = imgs[0] if imgs else ""
                    except Exception:
                        pass
                    item_title = listing.title or ""

                # Listingに無い場合、メッセージのsubjectから商品名を抽出
                if not item_title:
                    subj = msg.get("subject", "") if isinstance(msg, dict) else (msg.subject or "")
                    # "... about item #XXXXX ... - Product Title Here" パターン
                    if " - " in subj:
                        item_title = subj.split(" - ")[-1].strip()[:60]
                    elif subj:
                        item_title = subj[:60]

                # 画像がない場合、eBay Browse APIで取得を試みる
                if not thumbnail and iid:
                    try:
                        from ebay_core.client import get_item_details
                        details = get_item_details(iid)
                        if details and not details.get("error"):
                            img = details.get("image", {})
                            thumbnail = img.get("imageUrl", "")
                            if not item_title:
                                item_title = details.get("title", "")
                    except Exception:
                        pass

            item_map[iid] = {
                "item_id": iid if iid != "_no_item" else "",
                "title": item_title,
                "thumbnail": thumbnail,
                "unread_count": 0,
                "last_date": "",
                "buyers": {},
            }

        # バイヤー情報
        buyer_key = f"{msg.sender}|{iid}"
        if buyer_key not in item_map[iid]["buyers"]:
            # バイヤーステータス判定（購入済み/リピーター/返品等）
            buyer_status = _get_buyer_status(db, msg.sender)

            item_map[iid]["buyers"][buyer_key] = {
                "buyer": msg.sender,
                "item_id": iid if iid != "_no_item" else "",
                "last_date": msg.received_at.isoformat() if msg.received_at else "",
                "unread_count": 0,
                "total_count": 0,
                "sentiment": msg.sentiment or "",
                "status": buyer_status,
            }

        item_map[iid]["buyers"][buyer_key]["total_count"] += 1
        if not msg.is_read:
            item_map[iid]["buyers"][buyer_key]["unread_count"] += 1
            item_map[iid]["unread_count"] += 1

        # 最新日付を更新
        date_str = msg.received_at.isoformat() if msg.received_at else ""
        if date_str > item_map[iid]["last_date"]:
            item_map[iid]["last_date"] = date_str

        # 従来互換 conv_map
        conv_key = f"{msg.sender}|{msg.item_id}"
        if conv_key not in conv_map:
            conv_map[conv_key] = {
                "buyer": msg.sender,
                "item_id": msg.item_id,
                "item_title": item_map[iid]["title"],
                "thumbnail": item_map[iid]["thumbnail"],
                "subject": msg.subject,
                "last_message": msg.body[:100] if msg.body else "",
                "last_message_ja": (msg.body_translated or "")[:100],
                "last_date": date_str,
                "unread_count": 0,
                "total_count": 0,
                "sentiment": msg.sentiment or "",
            }
        conv_map[conv_key]["total_count"] += 1
        if not msg.is_read:
            conv_map[conv_key]["unread_count"] += 1

    # 商品リストを整形
    items = []
    for iid, item in sorted(item_map.items(), key=lambda x: x[1]["last_date"], reverse=True):
        buyer_list = sorted(item["buyers"].values(), key=lambda b: b["last_date"], reverse=True)
        items.append({
            "item_id": item["item_id"],
            "title": item["title"],
            "thumbnail": item["thumbnail"],
            "unread_count": item["unread_count"],
            "last_date": item["last_date"],
            "buyers": buyer_list,
        })

    conversations = sorted(conv_map.values(), key=lambda c: c["last_date"], reverse=True)
    return {"items": items[:limit], "conversations": conversations[:limit]}


def get_thread(db: Session, buyer: str, item_id: str = "") -> list[dict]:
    """特定バイヤーとのスレッドを取得する。"""
    query = db.query(BuyerMessage).filter(
        ((BuyerMessage.sender == buyer) | (BuyerMessage.recipient == buyer))
    )
    if item_id:
        query = query.filter(BuyerMessage.item_id == item_id)

    messages = query.order_by(BuyerMessage.received_at.asc()).all()

    result = []
    for msg in messages:
        # eBayシステムメッセージかどうか判定
        is_system = msg.sender == "eBay" and msg.direction == "inbound"
        direction = "system" if is_system else msg.direction

        result.append({
            "id": msg.id,
            "ebay_message_id": msg.ebay_message_id,
            "direction": direction,
            "sender": msg.sender,
            "subject": msg.subject,
            "body": msg.body,
            "body_translated": msg.body_translated or "",
            "is_read": bool(msg.is_read),
            "has_attachment": bool(msg.has_attachment),
            "attachment_urls": json.loads(msg.attachment_urls_json) if msg.attachment_urls_json else [],
            "draft_reply": msg.draft_reply or "",
            "sentiment": msg.sentiment or "",
            "urgency": msg.urgency or "",
            "sentiment_note": msg.sentiment_note or "",
            "response_time_min": msg.response_time_min,
            "received_at": msg.received_at.isoformat() if msg.received_at else "",
            "item_id": msg.item_id,
        })
    return result


# ── AI返信ドラフト ───────────────────────────────────────

REPLY_SYSTEM_PROMPT = """あなたはeBayセラーのカスタマーサポートAIアシスタントです。

あなたの役割:
- バイヤーからのメッセージに対して、プロフェッショナルで丁寧な返信ドラフトを作成する
- 日本からの輸出セラーとしての立場を理解し、適切な対応をする

重要ルール:
1. 返信は必ず英語で作成する
2. 丁寧で親切なトーン
3. 具体的な情報を含める（追跡番号、到着予定、返品ポリシー等）
4. 問題がある場合は解決策を提示する
5. 「日本から発送」「丁寧な梱包」等の付加価値をさりげなく伝える

返信本文のみを出力。JSON不要。"""


async def generate_draft(
    db: Session,
    message_id: int,
) -> dict:
    """メッセージに対するAI返信ドラフトを生成する。"""
    msg = db.query(BuyerMessage).filter(BuyerMessage.id == message_id).first()
    if not msg:
        return {"error": "Message not found"}

    # 同じバイヤーの過去メッセージを文脈として取得
    history = db.query(BuyerMessage).filter(
        ((BuyerMessage.sender == msg.sender) | (BuyerMessage.recipient == msg.sender)),
        BuyerMessage.id != message_id,
    ).order_by(BuyerMessage.received_at.desc()).limit(5).all()

    context = ""
    if history:
        context = "\n--- Previous conversation ---\n"
        for h in reversed(history):
            direction = "Buyer" if h.direction == "inbound" else "Seller"
            context += f"{direction}: {h.body[:200]}\n"

    prompt = f"""Reply to this eBay buyer message:

FROM: {msg.sender}
SUBJECT: {msg.subject}
ITEM ID: {msg.item_id}

MESSAGE:
{msg.body}
{context}
---
Write a professional English reply."""

    try:
        resp = _get_anthropic().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=REPLY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        draft = resp.content[0].text.strip()

        # DBに保存
        msg.draft_reply = draft
        db.commit()

        return {
            "message_id": msg.id,
            "draft_reply": draft,
            "original_body": msg.body,
            "buyer": msg.sender,
        }
    except Exception as e:
        logger.error(f"ドラフト生成エラー: {e}")
        return {"error": str(e)}


# ── メッセージ送信 ───────────────────────────────────────

async def send_reply(
    db: Session,
    buyer: str,
    item_id: str,
    body_en: str,
    subject: str = "",
    image_urls: list[str] | None = None,
) -> dict:
    """バイヤーにメッセージを送信してDBに保存する。"""
    result = send_buyer_message(
        item_id=item_id,
        recipient_id=buyer,
        body=body_en,
        subject=subject,
        image_urls=image_urls,
    )

    if result["success"]:
        # 返信時間をトラッキング
        try:
            from chat.intelligence import track_response_time
            track_response_time(db, buyer, item_id)
        except Exception as e:
            logger.warning(f"返信時間トラッキングエラー: {e}")

        # 送信メッセージをDBに保存
        outbound = BuyerMessage(
            ebay_message_id=f"out_{datetime.utcnow().timestamp()}",
            item_id=item_id,
            sender="me",
            recipient=buyer,
            direction="outbound",
            subject=subject,
            body=body_en,
            is_read=1,
            responded=1,
            has_attachment=1 if image_urls else 0,
            attachment_urls_json=json.dumps(image_urls) if image_urls else "[]",
            received_at=datetime.utcnow(),
            synced_at=datetime.utcnow(),
        )
        db.add(outbound)

        # 元メッセージをresponded = 1に
        last_inbound = db.query(BuyerMessage).filter(
            BuyerMessage.sender == buyer,
            BuyerMessage.item_id == item_id,
            BuyerMessage.direction == "inbound",
        ).order_by(BuyerMessage.received_at.desc()).first()
        if last_inbound:
            last_inbound.responded = 1

        db.commit()
        logger.info(f"返信送信完了: {buyer} (item={item_id})")

    return result


# ── 既読管理 ─────────────────────────────────────────────

def mark_read(db: Session, message_ids: list[int]) -> dict:
    """メッセージを既読にする（eBay API + ローカルDB）。"""
    messages = db.query(BuyerMessage).filter(BuyerMessage.id.in_(message_ids)).all()
    ebay_ids = [m.ebay_message_id for m in messages if m.ebay_message_id and not m.ebay_message_id.startswith("out_")]

    # eBay API
    if ebay_ids:
        mark_messages_read(ebay_ids, read=True)

    # ローカルDB
    for msg in messages:
        msg.is_read = 1
    db.commit()

    return {"success": True, "count": len(messages)}


def mark_all_read(db: Session) -> dict:
    """全未読メッセージを既読にする。"""
    unread = db.query(BuyerMessage).filter(
        BuyerMessage.is_read == 0,
        BuyerMessage.direction == "inbound",
    ).all()

    ebay_ids = [m.ebay_message_id for m in unread if m.ebay_message_id]
    if ebay_ids:
        # バッチ処理（最大25件ずつ）
        for i in range(0, len(ebay_ids), 25):
            mark_messages_read(ebay_ids[i:i+25], read=True)

    for msg in unread:
        msg.is_read = 1
    db.commit()

    return {"success": True, "count": len(unread)}


def mark_unread(db: Session, message_ids: list[int]) -> dict:
    """メッセージを未読に戻す。"""
    messages = db.query(BuyerMessage).filter(BuyerMessage.id.in_(message_ids)).all()
    ebay_ids = [m.ebay_message_id for m in messages if m.ebay_message_id and not m.ebay_message_id.startswith("out_")]

    if ebay_ids:
        mark_messages_read(ebay_ids, read=False)

    for msg in messages:
        msg.is_read = 0
    db.commit()

    return {"success": True, "count": len(messages)}


# ── テンプレート ─────────────────────────────────────────

def get_templates(db: Session, search: str = "", category: str = "") -> list[dict]:
    """テンプレート一覧を取得する。"""
    query = db.query(MessageTemplate).filter(MessageTemplate.is_active == 1)
    if search:
        query = query.filter(MessageTemplate.title.ilike(f"%{search}%"))
    if category:
        query = query.filter(MessageTemplate.category == category)

    templates = query.order_by(MessageTemplate.use_count.desc()).all()
    return [
        {
            "id": t.id,
            "title": t.title,
            "body_en": t.body_en,
            "body_ja": t.body_ja,
            "category": t.category,
            "variables": json.loads(t.variables_json) if t.variables_json else [],
            "use_count": t.use_count,
        }
        for t in templates
    ]


def save_template(db: Session, data: dict) -> dict:
    """テンプレートを作成/更新する。"""
    template_id = data.get("id")
    if template_id:
        tmpl = db.query(MessageTemplate).filter(MessageTemplate.id == template_id).first()
        if not tmpl:
            return {"error": "Template not found"}
    else:
        tmpl = MessageTemplate()
        db.add(tmpl)

    tmpl.title = data.get("title", tmpl.title)
    tmpl.body_en = data.get("body_en", tmpl.body_en)
    tmpl.body_ja = data.get("body_ja", tmpl.body_ja)
    tmpl.category = data.get("category", tmpl.category)
    tmpl.variables_json = json.dumps(data.get("variables", []))
    tmpl.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(tmpl)

    return {"success": True, "id": tmpl.id}


def delete_template(db: Session, template_id: int) -> dict:
    """テンプレートを削除（論理削除）する。"""
    tmpl = db.query(MessageTemplate).filter(MessageTemplate.id == template_id).first()
    if not tmpl:
        return {"error": "Template not found"}
    tmpl.is_active = 0
    db.commit()
    return {"success": True}


def use_template(db: Session, template_id: int) -> dict:
    """テンプレート使用回数をインクリメントする。"""
    tmpl = db.query(MessageTemplate).filter(MessageTemplate.id == template_id).first()
    if not tmpl:
        return {"error": "Template not found"}
    tmpl.use_count += 1
    db.commit()
    return {"id": tmpl.id, "body_en": tmpl.body_en, "body_ja": tmpl.body_ja}


# ── ユーティリティ ───────────────────────────────────────

def get_unread_count(db: Session) -> int:
    """未読メッセージ数を取得する。"""
    return db.query(func.count(BuyerMessage.id)).filter(
        BuyerMessage.is_read == 0,
        BuyerMessage.direction == "inbound",
    ).scalar() or 0


def _get_buyer_status(db: Session, buyer_username: str) -> list:
    """バイヤーのステータスアイコン用リストを返す。

    ステータス:
        purchased  — 購入済み (緑チェック)
        repeat     — リピーター (青リサイクル)
        shipped    — 発送済み (青トラック)
        delivered  — 納品済み (緑パッケージ)
        offer      — オファー承諾 (緑ドル)
        feedback   — フィードバック済み (黄星)
        return     — 返品 (オレンジ矢印)
        cancel     — キャンセル (赤バツ)
        refund     — 返金 (オレンジドル)
        dispute    — ディスプート (赤警告)
    """
    statuses = []
    orders = db.query(SalesRecord).filter(SalesRecord.buyer_name == buyer_username).all()

    if orders:
        statuses.append("purchased")
        if len(orders) >= 2:
            statuses.append("repeat")

    for o in orders:
        p = (o.progress or "").lower()
        # 発送済み
        if p in ("発送済", "shipped", "発送済み") and "shipped" not in statuses:
            statuses.append("shipped")
        # 納品済み
        if p in ("納品済", "delivered", "納品済み") and "delivered" not in statuses:
            statuses.append("delivered")
        # 返品
        if p in ("返品", "returned", "return") and "return" not in statuses:
            statuses.append("return")
        # キャンセル
        if p in ("キャンセル", "cancelled", "cancel") and "cancel" not in statuses:
            statuses.append("cancel")
        # 返金
        if p in ("返金", "refunded", "refund") and "refund" not in statuses:
            statuses.append("refund")
        # ディスプート
        if p in ("dispute", "ディスプート") and "dispute" not in statuses:
            statuses.append("dispute")

    # オファー承諾（メッセージのsubjectから判定）
    offer_msgs = db.query(BuyerMessage).filter(
        BuyerMessage.sender == buyer_username,
        BuyerMessage.subject.ilike("%offer%"),
    ).first()
    if offer_msgs:
        statuses.append("offer")

    return statuses


def _parse_date(date_str: str) -> datetime | None:
    """eBay日付文字列をdatetimeに変換する。"""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None
