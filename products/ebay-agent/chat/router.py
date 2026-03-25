"""Chat API Router — /api/chat/* エンドポイント"""
from __future__ import annotations

import logging
import os
from typing import List, Optional

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from database.models import get_db
from chat import service
from chat.translation import translate_to_ja, translate_to_en, suggest_alternatives

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ── Request Models ───────────────────────────────────────

class SendRequest(BaseModel):
    buyer: str
    item_id: str
    body_en: str
    subject: str = ""
    image_urls: List[str] = []


class TranslateRequest(BaseModel):
    text: str
    direction: str = "en_to_ja"  # en_to_ja | ja_to_en


class DraftRequest(BaseModel):
    message_id: int


class MarkReadRequest(BaseModel):
    message_ids: List[int]


class TemplateRequest(BaseModel):
    id: Optional[int] = None
    title: str = ""
    body_en: str = ""
    body_ja: str = ""
    category: str = "custom"
    variables: List[str] = []


class AlternativesRequest(BaseModel):
    text: str
    lang: str = "en"


# ── 会話 ─────────────────────────────────────────────────

@router.get("/conversations")
async def list_conversations(
    status: str = "all",
    search: str = "",
    limit: int = 50,
):
    db = get_db()
    try:
        result = service.get_conversations(db, status=status, search=search, limit=limit)
        unread = service.get_unread_count(db)
        return {
            "items": result["items"],
            "conversations": result["conversations"],
            "unread_total": unread,
        }
    finally:
        db.close()


@router.get("/conversations/{buyer}")
async def get_thread(buyer: str, item_id: str = ""):
    db = get_db()
    try:
        thread = service.get_thread(db, buyer=buyer, item_id=item_id)
        return {"messages": thread, "buyer": buyer, "item_id": item_id}
    finally:
        db.close()


# ── 送信 ─────────────────────────────────────────────────

@router.post("/send")
async def send_message(req: SendRequest):
    db = get_db()
    try:
        result = await service.send_reply(
            db,
            buyer=req.buyer,
            item_id=req.item_id,
            body_en=req.body_en,
            subject=req.subject,
            image_urls=req.image_urls if req.image_urls else None,
        )
        return result
    finally:
        db.close()


# ── 翻訳 ─────────────────────────────────────────────────

@router.post("/translate")
async def translate(req: TranslateRequest):
    if req.direction == "en_to_ja":
        translated = await translate_to_ja(req.text)
    else:
        translated = await translate_to_en(req.text)
    return {"translated": translated, "direction": req.direction}


# ── AI ドラフト ──────────────────────────────────────────

@router.post("/draft")
async def generate_draft(req: DraftRequest):
    db = get_db()
    try:
        return await service.generate_draft(db, message_id=req.message_id)
    finally:
        db.close()


class RefineRequest(BaseModel):
    message_id: int
    current_draft: str
    instruction: str


@router.post("/draft/refine")
async def refine_draft(req: RefineRequest):
    db = get_db()
    try:
        return await service.refine_draft(
            db,
            message_id=req.message_id,
            current_draft=req.current_draft,
            instruction=req.instruction,
        )
    finally:
        db.close()


@router.post("/draft/alternatives")
async def get_alternatives(req: AlternativesRequest):
    alternatives = await suggest_alternatives(req.text, lang=req.lang)
    return {"alternatives": alternatives}


# ── 既読管理 ─────────────────────────────────────────────

@router.post("/mark-read")
async def mark_read(req: MarkReadRequest):
    db = get_db()
    try:
        return service.mark_read(db, message_ids=req.message_ids)
    finally:
        db.close()


@router.post("/mark-all-read")
async def mark_all_read():
    db = get_db()
    try:
        return service.mark_all_read(db)
    finally:
        db.close()


@router.post("/mark-unread")
async def mark_unread(req: MarkReadRequest):
    db = get_db()
    try:
        return service.mark_unread(db, message_ids=req.message_ids)
    finally:
        db.close()


# ── 同期 ─────────────────────────────────────────────────

@router.post("/sync")
async def sync_messages():
    db = get_db()
    try:
        result = await service.sync_messages(db, days=7)
        return result
    finally:
        db.close()


@router.get("/unread-count")
async def unread_count():
    db = get_db()
    try:
        count = service.get_unread_count(db)
        return {"unread": count}
    finally:
        db.close()


# ── 画像アップロード ─────────────────────────────────────

@router.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
    from ebay_core.client import upload_message_image
    import tempfile

    # 一時ファイルに保存
    suffix = os.path.splitext(file.filename or "image.jpg")[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = upload_message_image(tmp_path)
        return result
    finally:
        os.unlink(tmp_path)


# ── テンプレート ─────────────────────────────────────────

@router.get("/templates")
async def list_templates(search: str = "", category: str = ""):
    db = get_db()
    try:
        templates = service.get_templates(db, search=search, category=category)
        return {"templates": templates}
    finally:
        db.close()


@router.post("/templates")
async def create_template(req: TemplateRequest):
    db = get_db()
    try:
        return service.save_template(db, req.model_dump())
    finally:
        db.close()


@router.put("/templates/{template_id}")
async def update_template(template_id: int, req: TemplateRequest):
    db = get_db()
    try:
        data = req.model_dump()
        data["id"] = template_id
        return service.save_template(db, data)
    finally:
        db.close()


@router.delete("/templates/{template_id}")
async def delete_template(template_id: int):
    db = get_db()
    try:
        return service.delete_template(db, template_id)
    finally:
        db.close()


@router.post("/templates/{template_id}/use")
async def use_template(template_id: int):
    db = get_db()
    try:
        return service.use_template(db, template_id)
    finally:
        db.close()


# ── AI インテリジェンス ──────────────────────────────────

@router.get("/smart-replies/{message_id}")
async def smart_replies(message_id: int):
    """スマートリプライ候補3つを生成"""
    from chat.intelligence import get_smart_replies
    db = get_db()
    try:
        msg = db.query(BuyerMessage).filter(BuyerMessage.id == message_id).first()
        if not msg:
            return {"replies": []}
        replies = await get_smart_replies(msg.body)
        return {"replies": replies}
    finally:
        db.close()


@router.get("/buyer/{buyer}/score")
async def buyer_score(buyer: str):
    """バイヤースコアリング"""
    from chat.intelligence import get_buyer_score
    db = get_db()
    try:
        return get_buyer_score(db, buyer)
    finally:
        db.close()


@router.get("/buyer/{buyer}/sales")
async def buyer_sales(buyer: str, item_id: str = ""):
    """バイヤー売上連携情報"""
    from chat.intelligence import get_buyer_sales_info
    db = get_db()
    try:
        return get_buyer_sales_info(db, buyer, item_id)
    finally:
        db.close()


@router.post("/draft/learned")
async def learned_draft(req: DraftRequest):
    """過去のスタイルを学習したAIドラフト"""
    from chat.intelligence import generate_learned_draft
    db = get_db()
    try:
        msg = db.query(BuyerMessage).filter(BuyerMessage.id == req.message_id).first()
        if not msg:
            return {"error": "Message not found"}
        draft = await generate_learned_draft(db, msg.body, msg.sender, msg.item_id)
        if draft:
            msg.draft_reply = draft
            db.commit()
        return {"draft_reply": draft, "message_id": req.message_id}
    finally:
        db.close()


@router.get("/response-stats")
async def response_stats():
    """返信時間統計"""
    from chat.intelligence import get_response_time_stats
    db = get_db()
    try:
        return get_response_time_stats(db)
    finally:
        db.close()


# ── 自動メッセージルール ─────────────────────────────────

class AutoRuleRequest(BaseModel):
    id: Optional[int] = None
    event_type: str = ""
    name: str = ""
    template_id: int = 0
    repeat_buyer_template_id: Optional[int] = None
    is_active: int = 1
    delay_minutes: int = 0


class ExcludeRequest(BaseModel):
    buyer_username: str
    reason: str = ""


@router.get("/auto-rules")
async def list_auto_rules():
    from chat.auto_message import get_rules
    db = get_db()
    try:
        return {"rules": get_rules(db)}
    finally:
        db.close()


@router.post("/auto-rules")
async def create_auto_rule(req: AutoRuleRequest):
    from chat.auto_message import save_rule
    db = get_db()
    try:
        return save_rule(db, req.model_dump())
    finally:
        db.close()


@router.put("/auto-rules/{rule_id}")
async def update_auto_rule(rule_id: int, req: AutoRuleRequest):
    from chat.auto_message import save_rule
    db = get_db()
    try:
        data = req.model_dump()
        data["id"] = rule_id
        return save_rule(db, data)
    finally:
        db.close()


@router.put("/auto-rules/{rule_id}/toggle")
async def toggle_auto_rule(rule_id: int):
    from chat.auto_message import toggle_rule
    db = get_db()
    try:
        return toggle_rule(db, rule_id)
    finally:
        db.close()


@router.delete("/auto-rules/{rule_id}")
async def delete_auto_rule(rule_id: int):
    from chat.auto_message import delete_rule
    db = get_db()
    try:
        return delete_rule(db, rule_id)
    finally:
        db.close()


@router.get("/exclude-list")
async def list_excludes():
    from chat.auto_message import get_exclude_list
    db = get_db()
    try:
        return {"excludes": get_exclude_list(db)}
    finally:
        db.close()


@router.post("/exclude-list")
async def add_exclude_buyer(req: ExcludeRequest):
    from chat.auto_message import add_exclude
    db = get_db()
    try:
        return add_exclude(db, req.buyer_username, req.reason)
    finally:
        db.close()


@router.delete("/exclude-list/{exclude_id}")
async def remove_exclude_buyer(exclude_id: int):
    from chat.auto_message import remove_exclude
    db = get_db()
    try:
        return remove_exclude(db, exclude_id)
    finally:
        db.close()


@router.get("/auto-logs")
async def list_auto_logs(limit: int = 50):
    from chat.auto_message import get_auto_message_logs
    db = get_db()
    try:
        return {"logs": get_auto_message_logs(db, limit)}
    finally:
        db.close()


# ── 商品詳細 (item_id で検索) ────────────────────────────

_item_cache = {}  # item_id → {data, ts}
_ITEM_CACHE_TTL = 1800  # 30分

@router.get("/item/{item_id}")
async def get_item_info(item_id: str):
    """item_idで商品情報を取得（Listing DB + Browse API fallback + キャッシュ）"""
    import time
    # キャッシュチェック
    cached = _item_cache.get(item_id)
    if cached and (time.time() - cached["ts"]) < _ITEM_CACHE_TTL:
        return cached["data"]

    from database.models import Listing
    import json as _json
    db = get_db()
    try:
        listing = db.query(Listing).filter(Listing.listing_id == item_id).first()
        if listing:
            imgs = []
            try:
                imgs = _json.loads(listing.image_urls_json) if listing.image_urls_json else []
            except Exception:
                pass
            result = {
                "sku": listing.sku,
                "title": listing.title,
                "price_usd": listing.price_usd,
                "quantity": listing.quantity,
                "category": listing.category_name,
                "condition": listing.condition,
                "listing_id": listing.listing_id,
                "thumbnail": imgs[0] if imgs else "",
                "seo_score": listing.seo_score,
            }
            _item_cache[item_id] = {"data": result, "ts": time.time()}
            return result
        # Browse API fallback
        from ebay_core.client import get_item_details
        details = get_item_details(item_id)
        if details:
            result = {
                "sku": "",
                "title": details.get("title", ""),
                "price_usd": float(details.get("price", {}).get("value", 0)),
                "quantity": details.get("estimatedAvailabilities", [{}])[0].get("estimatedAvailableQuantity", 0) if details.get("estimatedAvailabilities") else 0,
                "category": "",
                "condition": details.get("condition", ""),
                "listing_id": item_id,
                "thumbnail": details.get("image", {}).get("imageUrl", ""),
            }
            _item_cache[item_id] = {"data": result, "ts": time.time()}
            return result
        return {"error": "Not found"}
    finally:
        db.close()


@router.get("/buyer/{buyer}/details")
async def buyer_details(buyer: str, item_id: str = ""):
    """バイヤーの詳細情報（名前・住所・電話番号）をFulfillment APIから取得"""
    db = get_db()
    try:
        # item_id経由でSalesRecordのorder_idを取得
        from database.models import SalesRecord, BuyerMessage
        order_id = None

        # 直接マッチ
        sale = db.query(SalesRecord).filter(SalesRecord.buyer_name == buyer).order_by(SalesRecord.sold_at.desc()).first()
        if not sale and item_id:
            sale = db.query(SalesRecord).filter(SalesRecord.item_id == item_id).first()
        if not sale:
            buyer_items = [m.item_id for m in db.query(BuyerMessage.item_id).filter(
                BuyerMessage.sender == buyer, BuyerMessage.item_id != ""
            ).distinct().all()]
            if buyer_items:
                sale = db.query(SalesRecord).filter(SalesRecord.item_id.in_(buyer_items)).first()

        if not sale:
            return {"buyer_id": buyer, "full_name": "", "country": "", "address": "", "phone": "", "email": ""}

        # Fulfillment APIから注文詳細を取得
        from ebay_core.client import get_access_token
        import requests as req
        token = get_access_token()
        api_order_id = sale.order_id.replace("-", "-")  # eBay format
        resp = req.get(
            f"https://api.ebay.com/sell/fulfillment/v1/order/{api_order_id}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=15,
        )
        if resp.status_code != 200:
            return {"buyer_id": buyer, "full_name": sale.buyer_name or "", "country": sale.buyer_country or "", "address": "", "phone": "", "email": ""}

        order_data = resp.json()
        buyer_data = order_data.get("buyer", {})
        reg_addr = buyer_data.get("buyerRegistrationAddress", {})
        ship_instr = order_data.get("fulfillmentStartInstructions", [{}])
        ship_to = ship_instr[0].get("shippingStep", {}).get("shipTo", {}) if ship_instr else {}

        contact = ship_to.get("contactAddress", {})
        address_parts = [contact.get("addressLine1", ""), contact.get("addressLine2", "")]
        city = contact.get("city", "")
        state = contact.get("stateOrProvince", "")
        postal = contact.get("postalCode", "")
        country = contact.get("countryCode", "")
        full_address = ", ".join(p for p in [*address_parts, city, state, postal, country] if p)

        return {
            "buyer_id": buyer,
            "full_name": ship_to.get("fullName", reg_addr.get("fullName", sale.buyer_name or "")),
            "country": country or sale.buyer_country or "",
            "address": full_address,
            "phone": ship_to.get("primaryPhone", {}).get("phoneNumber", ""),
            "email": ship_to.get("email", ""),
        }
    finally:
        db.close()


# ── バイヤー履歴・トラブル・商品編集 (Phase 3) ──────────

@router.get("/buyer/{buyer}/history")
async def buyer_full_history(buyer: str):
    """バイヤー完全購入履歴（注文・追跡・トラブル・メッセージ数）"""
    from chat.buyer_history import get_buyer_full_history
    db = get_db()
    try:
        return get_buyer_full_history(db, buyer)
    finally:
        db.close()


@router.get("/buyer/{buyer}/troubles")
async def buyer_troubles(buyer: str):
    """バイヤーのリターン・キャンセル一覧"""
    from chat.trouble import get_troubles_for_buyer
    return get_troubles_for_buyer(buyer)


@router.get("/order/{order_id}/trouble")
async def order_trouble(order_id: str):
    """特定注文のトラブル状態"""
    from chat.trouble import get_troubles_for_order
    return get_troubles_for_order(order_id)


@router.get("/order/{order_id}/tracking")
async def order_tracking(order_id: str):
    """特定注文の追跡情報 + キャリアリンク"""
    from chat.buyer_history import get_order_tracking
    db = get_db()
    try:
        return get_order_tracking(db, order_id)
    finally:
        db.close()


@router.post("/order/{order_id}/cancel/accept")
async def accept_cancel_request(order_id: str):
    """キャンセルリクエストを承認"""
    from chat.trouble import accept_cancel
    # order_idからcancel_idを取得
    from ebay_core.client import get_cancellation_requests
    cancels = get_cancellation_requests(order_id=order_id)
    if not cancels:
        return {"error": "No cancellation found for this order"}
    return accept_cancel(cancels[0]["cancel_id"])


@router.post("/order/{order_id}/cancel/decline")
async def decline_cancel_request(order_id: str):
    """キャンセルリクエストを拒否"""
    from chat.trouble import decline_cancel
    from ebay_core.client import get_cancellation_requests
    cancels = get_cancellation_requests(order_id=order_id)
    if not cancels:
        return {"error": "No cancellation found for this order"}
    return decline_cancel(cancels[0]["cancel_id"])


class ListingEditRequest(BaseModel):
    price_usd: Optional[float] = None
    quantity: Optional[int] = None
    sku: Optional[str] = None


@router.put("/listing/{item_id}/edit")
async def edit_listing_from_chat(item_id: str, req: ListingEditRequest):
    """チャット内から商品編集（価格・数量）"""
    from chat.buyer_history import edit_listing_from_chat as _edit
    db = get_db()
    try:
        updates = {k: v for k, v in req.model_dump().items() if v is not None}
        return _edit(db, item_id, updates)
    finally:
        db.close()


# モデルインポート
from database.models import BuyerMessage
