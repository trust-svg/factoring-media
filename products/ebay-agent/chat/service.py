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

_client: anthropic.AsyncAnthropic | None = None


def _get_anthropic() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic()
    return _client


# ── メッセージ同期 ───────────────────────────────────────

async def sync_messages(db: Session, days: int = 30) -> dict:
    """eBay APIからメッセージを取得してDBに同期する。

    重要: eBay API呼び出し前にDBセッションを閉じることで
    長時間のDBロック保持を防ぐ。
    """
    from database.models import SessionLocal as _SessionLocal
    # ① DBセッションを使い捨て（eBay API呼び出し前に完結）
    with _SessionLocal() as check_db:
        existing_count = check_db.query(BuyerMessage).count()
        existing_ids = set(
            r[0] for r in check_db.query(BuyerMessage.ebay_message_id).all()
        )

    # 初回（DBが空）は90日分、以降は30日分で差分取得
    fetch_days = 90 if existing_count == 0 else days

    # ② eBay APIを呼ぶ（DBセッション不使用）
    raw_messages = get_buyer_messages(days=fetch_days, limit=200)

    new_count = 0
    updated_count = 0
    new_msgs = []
    update_ids = []  # (ebay_id, is_read, responded)

    for msg in raw_messages:
        ebay_id = msg["message_id"]
        if not ebay_id:
            continue

        if ebay_id in existing_ids:
            # 既読/返信済みステータスのみ追跡
            if msg["is_read"] or msg["responded"]:
                update_ids.append((ebay_id, msg["is_read"], msg["responded"]))
        else:
            # 新規メッセージ
            body = msg.get("body", "")
            direction = msg.get("direction", "inbound")
            sender = msg.get("sender", "")
            recipient = msg.get("recipient", "me") if direction == "outbound" else "me"
            if direction == "outbound":
                sender = "me"

            attachment_urls = msg.get("attachment_urls", [])
            new_msgs.append(BuyerMessage(
                ebay_message_id=ebay_id,
                item_id=msg.get("item_id", ""),
                sender=sender,
                recipient=recipient,
                direction=direction,
                subject=msg.get("subject", ""),
                body=body,
                body_translated="",
                is_read=1 if msg["is_read"] else 0,
                responded=1 if msg["responded"] else 0,
                has_attachment=1 if attachment_urls else 0,
                attachment_urls_json=json.dumps(attachment_urls) if attachment_urls else "[]",
                sentiment="",
                urgency="",
                sentiment_note="",
                received_at=_parse_date(msg.get("received_date", "")),
                synced_at=datetime.utcnow(),
            ))
            new_count += 1

    # ③ 最短DBセッションで書き込み（eBay API完了後）
    if new_msgs or update_ids:
        with _SessionLocal() as write_db:
            for m in new_msgs:
                write_db.add(m)
            if update_ids:
                for ebay_id, is_read, responded in update_ids:
                    row = write_db.query(BuyerMessage).filter(
                        BuyerMessage.ebay_message_id == ebay_id
                    ).first()
                    if row:
                        changed = False
                        if is_read and not row.is_read:
                            row.is_read = 1; changed = True
                        if responded and not row.responded:
                            row.responded = 1; changed = True
                        if changed:
                            row.synced_at = datetime.utcnow()
                            updated_count += 1
            write_db.commit()

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

                # 画像がない場合 → 商品詳細APIで個別取得（/api/chat/item/{id}経由）
                # ここではBrowse APIを呼ばない（高速化のため）

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


async def translate_untranslated(db: Session, message_ids: list[int]):
    """未翻訳メッセージを並列バッチ翻訳する（最大5件同時）。"""
    import asyncio as _asyncio
    msgs = db.query(BuyerMessage).filter(
        BuyerMessage.id.in_(message_ids),
        (BuyerMessage.body_translated.is_(None)) | (BuyerMessage.body_translated == ""),
    ).filter(BuyerMessage.sender != "eBay").filter(BuyerMessage.body != "").all()

    if not msgs:
        return 0

    # 最大5件を並列翻訳（APIレート制限考慮）
    semaphore = _asyncio.Semaphore(5)

    async def _translate_one(msg):
        if not msg.body:
            return
        async with semaphore:
            try:
                translated = await translate_to_ja(msg.body)
                msg.body_translated = translated
            except Exception as e:
                logger.warning(f"翻訳エラー msg={msg.id}: {e}")

    await _asyncio.gather(*[_translate_one(m) for m in msgs])
    db.commit()
    return len(msgs)


def get_thread(db: Session, buyer: str, item_id: str = "") -> list[dict]:
    """特定バイヤーとのスレッドを取得する。
    eBayシステム通知（オファー/Sold/Cancel等）も同じitem_idで紐付けて含める。
    """
    buyer_filter = (BuyerMessage.sender == buyer) | (BuyerMessage.recipient == buyer)

    if item_id:
        # バイヤーメッセージ + 同item_idのeBayシステム通知を両方含める
        ebay_system_filter = (BuyerMessage.sender == "eBay") & (BuyerMessage.item_id == item_id)
        query = db.query(BuyerMessage).filter(
            (buyer_filter | ebay_system_filter) & (BuyerMessage.item_id == item_id)
        )
    else:
        query = db.query(BuyerMessage).filter(buyer_filter)

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

REPLY_SYSTEM_PROMPT = """You are Roki, eBay seller at "Samurai Shop Japan SELECT" (Japan).
You sell: samurai armor, vintage audio/music gear, cameras, Japanese antiques.

═══ CORE PHILOSOPHY ═══
- Every interaction builds long-term trust → repeat buyers
- Make them think "I want to buy from this person again"
- Troubles are opportunities to INCREASE trust

═══ LANGUAGE ═══
- Detect buyer's language → reply in THAT language
- German: "Sie" form, "Herr/Frau + Nachname" (never 様), sign off "Mit freundlichen Grüßen\nRoki"
- French: "vous" form, sign off "Cordialement,\nRoki"
- English: sign off "Best regards,\nRoki"
- Other: match their language

═══ MESSAGE STRUCTURE (always follow) ═══
1. Greeting + name (if available)
2. Gratitude (for purchase/message/interest)
3. Empathy (understand their concern/request)
4. Answer (simple, specific, actionable)
5. Reassurance (inspection, packing, shipping safety)
6. Added value (suggestion, alternative, support offer)
7. Closing (always available + sincere appreciation)

═══ TONE ═══
- Professional + warm (not robotic, not too casual)
- Sincere, reassuring, considerate
- Always include gratitude
- Empathize with buyer's feelings
- For high-value items: elevate formality to match prestige
- "あなたのために対応している感" = personalized attention

═══ KEY PHRASES (use naturally) ═══
Reassurance:
- "Please rest assured..." / "We have carefully inspected..."
- "We will pack it securely..." / "shipped from Japan with care"
Empathy:
- "I completely understand your concern."
Gratitude:
- "I truly appreciate your trust."
Relationship:
- "I look forward to serving you again."
- "お取引できることを嬉しく思います" → localize to buyer's language

═══ DIFFERENTIATION ═══
- Always mention: final inspection before shipping
- Emphasize: careful packing (FRAGILE, protective materials)
- Worldwide shipping experience → reliability
- Post-purchase support ("いつでもご連絡ください")
- "I can also source other items for you" (show procurement power)
- Make it feel individually handled, not template-based

═══ SITUATION FLOWS (follow strictly) ═══

🟡 PRICE NEGOTIATION:
gratitude → understanding → price justification (market value, condition) → firm limit → soft close
- Counter: 10-15% below listing (max). Present as "the best I can do"
- Single counter only — avoid back-and-forth haggling
- Lowball (30%+ off): explain market value, give a larger counter at reasonable level
- Frame current price as "already competitive" before countering
- Bundle discounts are powerful closers (combine shipping saves cost)
- "I would be happy to proceed right away" → urgency nudge
- "This is just an optional suggestion" → never pushy (critical for EU)
- If declining: never say "No" — say "difficult to reduce significantly"

🔴 COMPLAINT/TROUBLE:
apology → empathy → solution (return/refund/partial refund) → sincerity
- ALWAYS apologize first, never make excuses or dispute buyer's description
- Present 2-3 options: full refund with return / partial refund to keep / exchange
- PayPal refund = NEVER → eBay partial refund only
- VAT issues: explain eBay's system, provide screenshots
- For international returns: offer "keep item + partial refund" to avoid shipping cost
- Always offer cancellation as last resort (builds massive trust)
- "I sincerely apologize for the inconvenience caused."
- "As a gesture of goodwill, I would like to offer..."

🔵 TRUST/ANXIETY:
track record → inspection details → packing quality → ongoing support
- Mention years of experience, worldwide shipping
- "We inspect every item before shipping"
- "Packed with protective materials, marked FRAGILE"
- "I'm always available if you have any questions after purchase"
- For technical items (audio, DJ gear, cameras): demonstrate product knowledge

🟢 POST-PURCHASE:
gratitude → reassurance (shipping timeline, tracking) → repeat buyer nudge
- "Thank you so much for your purchase"
- Share shipping schedule and tracking when available
- "I look forward to serving you again in the future"
- "I can also search for specific items from Japan if you're looking for something particular"

🔵 CANCELLATION:
- Buyer-requested: "No problem at all, I will process right away"
- Stock issue: sincere apology → offer alternative → future discount

═══ CROSS-SELL ═══
- Mention related products naturally with eBay links
- "Falls Sie einen Ständer benötigen..." / "If you need..."
- Always clarify: "optional, no pressure"

═══ NG (never do) ═══
- Cold/bureaucratic tone
- One-sided rejection
- Too-short replies that leave anxiety
- "Your eBay Store" (always "Roki")
- Subject lines, "---", markdown, meta-commentary

═══ GOAL ═══
- ★5 feedback on every transaction
- Turn complaints into trust
- Increase repeat buyers
- Maintain prices without alienating buyers

═══ OUTPUT FORMAT ═══
Output THREE clearly separated sections:

**REPLY**
(The complete message in buyer's detected language, ready to send on eBay. No subject lines, no headers.)

**JA**
(Japanese translation of the reply for seller confirmation)

**STRATEGY**
(1-2 line strategy note in Japanese: what approach was taken and why)

Rules:
- Proper line breaks for readability
- Sign off as "Roki"
- End positively, always
- No markdown formatting, no "---", no "Here is..." meta-commentary"""


ANALYSIS_SYSTEM_PROMPT = """あなたはeBay輸出ビジネスのアドバイザーです。セラーはRoki（日本から発送）。

バイヤーのメッセージを分析し、以下を日本語で出力してください。

出力形式（この通りに出力）:

## バイヤーの意味
メッセージの内容を簡潔に日本語で説明（2-3行）
バイヤーの言語も記載

## タイプ
以下のどれかを1つ選び、対応フローを明記:
- 🟡 価格交渉 → 感謝→理解→価格の根拠→限界提示→柔らかく締め
- 🔴 クレーム/トラブル → 謝罪→共感→解決策提示→誠意
- 🔵 信頼不安/質問 → 実績→検品→梱包→サポート
- 🟢 購入後/ポジティブ → 感謝→安心→リピーター誘導

## 戦略アドバイス
- 交渉: オファーの妥当性（出品価格の何%か）、推奨カウンター価格、値引き上限
- クレーム: eBay規約に沿った対応、PayPal返金はNG
- 質問: 回答のポイント・注意点
- ポジティブ: リピーター化・クロスセルのチャンス

ルール:
- 出品価格が提供された場合、%計算を含めて分析
- 簡潔に（全体で12行以内）
- マークダウンは ## と - のみ"""


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

    # 出品価格情報を取得
    price_info = ""
    if msg.item_id:
        listing = db.query(Listing).filter(Listing.listing_id == msg.item_id).first()
        if listing:
            price_info = f"\nLISTING PRICE: ${listing.price_usd:.2f} USD"

    # バイヤースコア情報
    from chat.intelligence import get_buyer_score
    score = get_buyer_score(db, msg.sender)
    buyer_info = f"\nBUYER: {msg.sender} | Tier: {score['tier']} | Orders: {score['total_orders']} | Spent: ${score['total_spent_usd']} | Troubles: {score['trouble_count']}"

    # SalesRecord情報
    sale_info = ""
    if msg.item_id:
        sale = db.query(SalesRecord).filter(SalesRecord.item_id == msg.item_id).first()
        if sale:
            sale_info = f"\nORDER: {sale.order_id} | Status: {sale.progress} | Tracking: {sale.tracking_number or 'N/A'}"

    prompt = f"""Reply to this eBay buyer message:

FROM: {msg.sender}
SUBJECT: {msg.subject}
ITEM ID: {msg.item_id}{price_info}{buyer_info}{sale_info}

MESSAGE:
{msg.body}
{context}
---
Detect the buyer's language and reply in THAT language. Follow the output format in your system prompt."""

    try:
        # 1. 分析（バイヤーの意味 + 戦略アドバイス）
        analysis = ""
        try:
            analysis_prompt = f"""バイヤーメッセージを分析してください。

FROM: {msg.sender}
ITEM ID: {msg.item_id}{price_info}{buyer_info}{sale_info}

MESSAGE:
{msg.body}
{context}"""

            analysis_resp = await _get_anthropic().messages.create(
                model="claude-sonnet-4-6",
                max_tokens=500,
                system=ANALYSIS_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": analysis_prompt}],
            )
            analysis = analysis_resp.content[0].text.strip()
        except Exception as e:
            logger.warning(f"分析生成エラー: {e}")

        # 2. 返信ドラフト（バイヤーの言語で + JA + STRATEGY を一括生成）
        resp = await _get_anthropic().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=REPLY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_output = resp.content[0].text.strip()

        # 3セクション分割: REPLY / JA / STRATEGY
        draft, draft_ja, strategy = _parse_draft_sections(raw_output)
        draft = _clean_draft(draft)

        # 分析にSTRATEGYを追加
        if strategy and analysis:
            analysis = f"{analysis}\n\n## 返信戦略\n{strategy}"
        elif strategy:
            analysis = f"## 返信戦略\n{strategy}"

        # DBに保存
        msg.draft_reply = draft
        db.commit()

        return {
            "message_id": msg.id,
            "draft_reply": draft,
            "draft_reply_ja": draft_ja,
            "analysis": analysis,
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

    注意: SalesRecordのbuyer_nameは実名、BuyerMessageのsenderはeBay ID。
    直接マッチしないため、メッセージのitem_id経由でSalesRecordを検索する。
    """
    statuses = []

    # このバイヤーのメッセージからitem_idを取得
    buyer_item_ids = [
        m.item_id for m in db.query(BuyerMessage.item_id).filter(
            BuyerMessage.sender == buyer_username,
            BuyerMessage.item_id != "",
        ).distinct().all()
    ]

    # SalesRecordを検索: buyer_name直接 OR item_id経由
    # （eBay IDと実名が異なるため item_id フォールバックが必要）
    orders = db.query(SalesRecord).filter(
        SalesRecord.buyer_name == buyer_username
    ).all()
    if not orders and buyer_item_ids:
        # item_idが一致するSalesRecordを検索（購入済み判定のみに使用）
        orders = db.query(SalesRecord).filter(
            SalesRecord.item_id.in_(buyer_item_ids)
        ).all()

    if orders:
        statuses.append("purchased")
        if len(orders) >= 2:
            statuses.append("repeat")

    for o in orders:
        p = (o.progress or "").lower()
        if p in ("発送済", "shipped", "発送済み") and "shipped" not in statuses:
            statuses.append("shipped")
        if p in ("納品済", "delivered", "納品済み") and "delivered" not in statuses:
            statuses.append("delivered")
        if p in ("返品", "returned", "return") and "return" not in statuses:
            statuses.append("return")
        if p in ("キャンセル", "cancelled", "cancel") and "cancel" not in statuses:
            statuses.append("cancel")
        if p in ("返金", "refunded", "refund") and "refund" not in statuses:
            statuses.append("refund")
        if p in ("dispute", "ディスプート") and "dispute" not in statuses:
            statuses.append("dispute")

    # オファー関連（メッセージのsubjectから判定）
    offer_msgs = db.query(BuyerMessage).filter(
        BuyerMessage.sender == buyer_username,
        BuyerMessage.subject.ilike("%offer%"),
    ).first()
    if offer_msgs:
        statuses.append("offer")

    # フィードバック（eBayメッセージのsubjectから判定）
    feedback_msg = db.query(BuyerMessage).filter(
        BuyerMessage.sender == "eBay",
        BuyerMessage.subject.ilike("%feedback%"),
        BuyerMessage.item_id.in_(buyer_item_ids) if buyer_item_ids else False,
    ).first()
    if feedback_msg:
        statuses.append("feedback")

    # メッセージのやり取りがある（ステータスがまだ空の場合）
    if not statuses:
        has_thread = db.query(BuyerMessage).filter(
            BuyerMessage.sender == buyer_username
        ).first()
        if has_thread:
            statuses.append("message")

    return statuses


def _parse_draft_sections(raw: str) -> tuple:
    """AI出力を REPLY / JA / STRATEGY の3セクションに分割する。"""
    import re
    reply = ""
    ja = ""
    strategy = ""

    # セクションヘッダーで分割
    sections = re.split(r'\*\*(?:REPLY|JA|STRATEGY)\*\*\s*\n?', raw)
    if len(sections) >= 4:
        reply = sections[1].strip()
        ja = sections[2].strip()
        strategy = sections[3].strip()
    elif len(sections) >= 3:
        reply = sections[1].strip()
        ja = sections[2].strip()
    elif len(sections) >= 2:
        reply = sections[1].strip()
    else:
        # フォールバック: セクションヘッダーなし → 全体をreplyとして扱う
        reply = raw.strip()

    return reply, ja, strategy


def _clean_draft(draft: str) -> str:
    """AIドラフトから不要なヘッダー/フッターを除去する。"""
    import re
    lines = draft.split("\n")
    clean = []
    skip = False
    for line in lines:
        stripped = line.strip()
        # 不要な行をスキップ
        if re.match(r"^(Subject:|Re:|---+$|Here is|Below is|Draft:)", stripped, re.IGNORECASE):
            continue
        if re.match(r"^\*\*Your eBay Store\*\*", stripped):
            continue
        if stripped == "---":
            continue
        clean.append(line)

    result = "\n".join(clean).strip()

    # 署名がない場合は追加
    if "Roki" not in result:
        result += "\n\nBest regards,\nRoki"

    return result


async def refine_draft(
    db: Session,
    message_id: int,
    current_draft: str,
    instruction: str,
) -> dict:
    """ユーザーの指示に基づいてドラフトを修正する。"""
    msg = db.query(BuyerMessage).filter(BuyerMessage.id == message_id).first()
    if not msg:
        return {"error": "Message not found"}

    prompt = f"""Here is the current draft reply to an eBay buyer:

BUYER'S MESSAGE:
{msg.body}

CURRENT DRAFT:
{current_draft}

SELLER'S INSTRUCTION (in Japanese — understand and apply):
{instruction}

---
Rewrite the draft based on the seller's instruction.
IMPORTANT: Keep the SAME LANGUAGE as the current draft (if it's German, rewrite in German. If French, rewrite in French, etc.)
If the instruction is in Japanese, understand it but write the output in the draft's language.
Output ONLY the updated message body. Sign off as "Roki". No subject lines, no "---", no meta-commentary."""

    try:
        resp = await _get_anthropic().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=REPLY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        refined = _clean_draft(resp.content[0].text.strip())

        # 日本語訳
        refined_ja = ""
        try:
            refined_ja = await translate_to_ja(refined)
        except Exception:
            pass

        msg.draft_reply = refined
        db.commit()

        return {
            "message_id": msg.id,
            "draft_reply": refined,
            "draft_reply_ja": refined_ja,
        }
    except Exception as e:
        logger.error(f"ドラフト修正エラー: {e}")
        return {"error": str(e)}


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
