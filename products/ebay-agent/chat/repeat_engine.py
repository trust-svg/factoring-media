"""リピート購入エンジン Phase 1 — オーケストレーション層

過去に正常取引したバイヤーへ、ポジティブ Feedback 受信 + D7 待機 後に
半自動で再購入促進メッセージを送る。

eBay 規約参照:
- Member-to-Member Contact Policy:
  https://www.ebay.com/help/policies/member-behaviour-policies/contact-members-policy
- Send Offer to Buyer ドキュメント（Phase 3 用に保持）:
  https://developer.ebay.com/api-docs/sell/negotiation/overview.html
- Promotions Manager ドキュメント（Phase 2 用）:
  https://developer.ebay.com/api-docs/sell/marketing/overview.html

Phase 1 は Trading API send_buyer_message のみ。Negotiation API は呼ばない。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from config import (
    REPEAT_ENGINE_ALLOWLIST_BUYERS,
    REPEAT_ENGINE_DAILY_SEND_CAP,
    REPEAT_ENGINE_DRY_RUN,
    REPEAT_ENGINE_ENABLED,
)
from database.models import (
    AutoMessageLog,
    BuyerExclude,
    BuyerSegment,
    Listing,
    ListingCategoryRule,
    OutboundOffer,
    RepeatCampaign,
    SalesRecord,
    get_db,
)

logger = logging.getLogger(__name__)


# ── コンプライアンスチェック ───────────────────────────

_BLOCK_PATTERNS = [
    # 非 eBay 外部URL
    (
        "external_url",
        re.compile(r"https?://(?!(?:[\w-]+\.)?ebay(?:inc)?\.[a-z.]+)", re.IGNORECASE),
    ),
    ("email_address", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    (
        "off_platform_channel",
        re.compile(
            r"(?i)\b(whatsapp|telegram|wechat|instagram|facebook|tiktok|line\s*(?:app|chat))\b"
        ),
    ),
]

_WARN_PATTERNS = [
    (
        "pushy_sales",
        re.compile(r"(?i)\b(act now|hurry|last chance|limited time only)\b"),
    ),
]


def compliance_check(body: str) -> list[str]:
    """メッセージ本文の eBay 規約コンプライアンスチェック。

    返値: フラグ名のリスト（プレフィックスで block / warn を区別）
    block:* が 1 件でも立っていれば送信不可。
    """
    flags: list[str] = []
    for name, pat in _BLOCK_PATTERNS:
        if pat.search(body or ""):
            flags.append(f"block:{name}")
    for name, pat in _WARN_PATTERNS:
        if pat.search(body or ""):
            flags.append(f"warn:{name}")
    if body and len(body) > 800:
        flags.append("warn:length")
    return flags


def has_block_flag(flags: list[str]) -> bool:
    return any(f.startswith("block:") for f in flags)


# ── ジャンルタグ判定 ─────────────────────────────────

_DEFAULT_RULES: list[dict] = [
    {
        "rule_name": "Figures & Collectibles",
        "priority": 10,
        "ebay_category_id": "246",
        "title_regex": r"(?i)(figure|figma|nendoroid|プラモ|gundam|ガンプラ)",
        "min_price_usd": 0.0,
        "max_price_usd": 300.0,
        "category_tag": "figure_collectible",
        "cadence_bucket": "short_term",
    },
    {
        "rule_name": "Audio Collectibles",
        "priority": 20,
        "ebay_category_id": "175607",
        "title_regex": r"(?i)(walkman|cassette|vintage)",
        "min_price_usd": 0.0,
        "max_price_usd": 500.0,
        "category_tag": "audio_collectible",
        "cadence_bucket": "short_term",
    },
    {
        "rule_name": "Audio Premium",
        "priority": 30,
        "ebay_category_id": "175607",
        "title_regex": "",
        "min_price_usd": 500.0,
        "max_price_usd": 0.0,
        "category_tag": "audio_premium",
        "cadence_bucket": "long_term",
    },
    {
        "rule_name": "Watch Premium",
        "priority": 40,
        "ebay_category_id": "31387",
        "title_regex": "",
        "min_price_usd": 0.0,
        "max_price_usd": 0.0,
        "category_tag": "watch_premium",
        "cadence_bucket": "long_term",
    },
    {
        "rule_name": "Armor Premium",
        "priority": 50,
        "ebay_category_id": "13606",
        "title_regex": r"(?i)(甲冑|samurai|armor|kabuto)",
        "min_price_usd": 0.0,
        "max_price_usd": 0.0,
        "category_tag": "armor_premium",
        "cadence_bucket": "long_term",
    },
    {
        "rule_name": "Fallback",
        "priority": 999,
        "ebay_category_id": "",
        "title_regex": "",
        "min_price_usd": 0.0,
        "max_price_usd": 0.0,
        "category_tag": "other",
        "cadence_bucket": "long_term",
    },
]


def seed_default_rules(db: Session) -> int:
    """listing_category_rules が空ならデフォルトを投入。返値=追加件数。"""
    existing = db.query(ListingCategoryRule).count()
    if existing:
        return 0
    for rule in _DEFAULT_RULES:
        db.add(ListingCategoryRule(**rule, is_enabled=1))
    db.commit()
    return len(_DEFAULT_RULES)


def _manual_override_tag(cost_note: Optional[str]) -> Optional[str]:
    """sales_records.cost_note 内の `[cat:xxx]` を最優先で適用する。"""
    if not cost_note:
        return None
    m = re.search(r"\[cat:([a-z_]+)\]", cost_note)
    return m.group(1) if m else None


def classify_sale(db: Session, sale: SalesRecord) -> str:
    """SalesRecord の item_category_tag を決定する（既存値があれば尊重）。"""
    if sale.item_category_tag:
        return sale.item_category_tag

    override = _manual_override_tag(sale.cost_note)
    if override:
        return override

    listing = (
        db.query(Listing).filter(Listing.sku == sale.sku).first() if sale.sku else None
    )
    category_id = ""
    if listing:
        # Listing.category_id はあれば使う（モデルにあれば）
        category_id = getattr(listing, "category_id", "") or ""

    title = (sale.title or "") + " " + (listing.title if listing else "")
    price = sale.sale_price_usd or 0.0

    rules = (
        db.query(ListingCategoryRule)
        .filter(ListingCategoryRule.is_enabled == 1)
        .order_by(ListingCategoryRule.priority.asc(), ListingCategoryRule.id.asc())
        .all()
    )

    for r in rules:
        if r.ebay_category_id:
            if category_id:
                if r.ebay_category_id != category_id:
                    continue
            elif not r.title_regex:
                # category-only rule cannot be evaluated without a sale category
                continue
        if r.title_regex:
            try:
                if not re.search(r.title_regex, title):
                    continue
            except re.error:
                logger.warning(f"Invalid regex in rule {r.rule_name}: {r.title_regex}")
                continue
        if r.min_price_usd and price < r.min_price_usd:
            continue
        if r.max_price_usd and price > r.max_price_usd:
            continue
        return r.category_tag

    return "other"


# ── eligibility 計算 ─────────────────────────────────


def _is_excluded(db: Session, buyer: str) -> bool:
    if not buyer:
        return True
    return (
        db.query(BuyerExclude).filter(BuyerExclude.buyer_username == buyer).first()
        is not None
    )


def compute_eligibility(
    sale: SalesRecord, db: Session, now: Optional[datetime] = None
) -> int:
    """単一の SalesRecord に対して is_repeat_eligible を計算する（純粋関数）。"""
    now = now or datetime.utcnow()

    # 1. progress が正常完了
    if sale.progress in {"キャンセル", "返金"}:
        return 0
    if sale.progress not in {"発送済み", "納品済み"}:
        return 0

    # 2. delivered_at が 7日以上前
    if not sale.delivered_at or sale.delivered_at > now - timedelta(days=7):
        return 0

    # 3-4. refund / dispute 無し
    if sale.refund_status not in {"", "none"}:
        return 0
    if sale.dispute_status not in {"", "none"}:
        return 0

    # 5. Positive feedback あり OR (delivered 30日以上前 AND ネガティブ signal なし)
    positive = (sale.feedback_rating or "").lower() == "positive"
    silent_ok = sale.delivered_at <= now - timedelta(days=30) and (
        sale.feedback_rating or ""
    ).lower() not in {"negative", "neutral"}
    if not (positive or silent_ok):
        return 0

    # 6. exclude check
    if _is_excluded(db, sale.buyer_name):
        return 0

    return 1


def refresh_eligibility() -> dict:
    """夜間バッチ: 全 SalesRecord の is_repeat_eligible を再計算 + category_tag を埋める。"""
    if not REPEAT_ENGINE_ENABLED:
        logger.debug("refresh_eligibility skipped: REPEAT_ENGINE_ENABLED=false")
        return {"skipped": True}

    db = get_db()
    flipped = 0
    classified = 0
    try:
        # 過去 180 日のみ対象（古すぎる取引は計算しない）
        cutoff = datetime.utcnow() - timedelta(days=180)
        sales = db.query(SalesRecord).filter(SalesRecord.sold_at >= cutoff).all()

        # rules は一度だけ読む
        if db.query(ListingCategoryRule).count() == 0:
            seed_default_rules(db)

        for sale in sales:
            if not sale.item_category_tag:
                sale.item_category_tag = classify_sale(db, sale)
                classified += 1
            new_val = compute_eligibility(sale, db)
            if new_val != sale.is_repeat_eligible:
                sale.is_repeat_eligible = new_val
                flipped += 1
        db.commit()
        logger.info(
            f"refresh_eligibility: flipped={flipped} classified={classified} "
            f"scanned={len(sales)}"
        )
        return {"flipped": flipped, "classified": classified, "scanned": len(sales)}
    except Exception:
        logger.exception("refresh_eligibility failed")
        db.rollback()
        return {"error": True}
    finally:
        db.close()


# ── buyer_segments の再構築 ────────────────────────────


def rebuild_buyer_segments() -> dict:
    """夜間バッチ: sales_records から buyer_segments を UPSERT。"""
    if not REPEAT_ENGINE_ENABLED:
        logger.debug("rebuild_buyer_segments skipped: REPEAT_ENGINE_ENABLED=false")
        return {"skipped": True}

    db = get_db()
    upserts = 0
    try:
        # buyer_username × category_tag で集約
        rows = (
            db.query(
                SalesRecord.buyer_name.label("buyer"),
                SalesRecord.item_category_tag.label("tag"),
                func.count(SalesRecord.id).label("cnt"),
                func.sum(SalesRecord.sale_price_usd).label("spend"),
                func.max(SalesRecord.sold_at).label("last_purchase"),
                func.max(
                    case(
                        (
                            SalesRecord.feedback_rating == "Positive",
                            SalesRecord.feedback_received_at,
                        ),
                        else_=None,
                    )
                ).label("last_positive_fb"),
            )
            .filter(SalesRecord.buyer_name != "")
            .group_by(SalesRecord.buyer_name, SalesRecord.item_category_tag)
            .all()
        )

        for row in rows:
            seg = (
                db.query(BuyerSegment)
                .filter(
                    BuyerSegment.buyer_username == row.buyer,
                    BuyerSegment.category_tag == (row.tag or "other"),
                )
                .first()
            )
            if seg is None:
                seg = BuyerSegment(
                    buyer_username=row.buyer,
                    category_tag=row.tag or "other",
                )
                db.add(seg)
            seg.purchase_count = row.cnt or 0
            seg.total_spend_usd = float(row.spend or 0.0)
            seg.last_purchase_at = row.last_purchase
            if row.last_positive_fb:
                seg.last_positive_feedback_at = row.last_positive_fb
            # cadence_bucket は category_tag に紐付くデフォルトを使う
            seg.cadence_bucket = _cadence_for_tag(row.tag or "other")
            upserts += 1

        db.commit()
        logger.info(f"rebuild_buyer_segments: upserts={upserts}")
        return {"upserts": upserts}
    except Exception:
        logger.exception("rebuild_buyer_segments failed")
        db.rollback()
        return {"error": True}
    finally:
        db.close()


def _cadence_for_tag(tag: str) -> str:
    short = {"figure_collectible", "audio_collectible"}
    return "short_term" if tag in short else "long_term"


# ── トリガー: feedback_received(Positive) ─────────────


def enqueue_post_feedback(
    buyer_username: str,
    order_id: str,
    item_id: str,
    comment_text: str = "",
    rating: str = "Positive",
) -> dict:
    """webhook から呼ぶ。outbound_offers に due_at=now+7d の draft を作る。

    冪等: 同じ (buyer, item_id, trigger='post_feedback_d7') が既に存在すれば skip。
    """
    if not REPEAT_ENGINE_ENABLED:
        logger.debug("enqueue_post_feedback skipped: REPEAT_ENGINE_ENABLED=false")
        return {"skipped": "engine_disabled"}

    if (rating or "").lower() != "positive":
        return {"skipped": "non_positive"}

    if not buyer_username:
        return {"skipped": "no_buyer"}

    db = get_db()
    try:
        # feedback_rating / feedback_comment / feedback_received_at を SalesRecord に反映
        sale = None
        if order_id:
            sale = (
                db.query(SalesRecord).filter(SalesRecord.order_id == order_id).first()
            )
        if not sale and item_id and buyer_username:
            sale = (
                db.query(SalesRecord)
                .filter(
                    SalesRecord.item_id == item_id,
                    SalesRecord.buyer_name == buyer_username,
                )
                .order_by(SalesRecord.sold_at.desc())
                .first()
            )

        if sale:
            sale.feedback_rating = "Positive"
            sale.feedback_comment = comment_text or ""
            sale.feedback_received_at = datetime.utcnow()

        # opt-out チェック
        if _is_excluded(db, buyer_username):
            db.commit()
            return {"skipped": "excluded"}

        # 重複チェック
        send_item_id = item_id or (sale.item_id if sale else "")
        existing = (
            db.query(OutboundOffer)
            .filter(
                OutboundOffer.buyer_username == buyer_username,
                OutboundOffer.past_order_item_id == send_item_id,
                OutboundOffer.trigger == "post_feedback_d7",
                OutboundOffer.status.in_(
                    ("draft", "awaiting_approval", "approved", "sent")
                ),
            )
            .first()
        )
        if existing:
            db.commit()
            return {"skipped": "duplicate", "offer_id": existing.id}

        campaign = _ensure_campaign(db, "post_feedback_d7")
        offer = OutboundOffer(
            campaign_id=campaign.id,
            buyer_username=buyer_username,
            trigger="post_feedback_d7",
            past_order_item_id=send_item_id,
            past_sale_record_id=sale.id if sale else None,
            status="draft",
            due_at=datetime.utcnow() + timedelta(days=7),
        )
        db.add(offer)
        db.commit()
        logger.info(
            f"enqueue_post_feedback: offer_id={offer.id} buyer={buyer_username} "
            f"item={send_item_id}"
        )
        return {"enqueued": True, "offer_id": offer.id}
    except Exception:
        logger.exception("enqueue_post_feedback failed")
        db.rollback()
        return {"error": True}
    finally:
        db.close()


def _ensure_campaign(db: Session, code: str) -> RepeatCampaign:
    camp = db.query(RepeatCampaign).filter(RepeatCampaign.code == code).first()
    if camp is None:
        camp = RepeatCampaign(
            code=code,
            name="Post-Feedback D7",
            description="Positive Feedback 受信から 7 日後の再購入促進メッセージ",
            trigger_type="feedback_positive",
            cooldown_days=90,
            daily_cap=REPEAT_ENGINE_DAILY_SEND_CAP,
            is_enabled=1,
        )
        db.add(camp)
        db.commit()
        db.refresh(camp)
    return camp


# ── 15分おき: due_at 到達 draft を Claude で生成 ────────


def draft_pending_post_feedback() -> dict:
    """status='draft' AND due_at<=now AND draft_body='' を拾って Claude で下書き生成。"""
    if not REPEAT_ENGINE_ENABLED:
        logger.debug("draft_pending_post_feedback skipped: REPEAT_ENGINE_ENABLED=false")
        return {"skipped": True}

    from chat.repeat_drafts import generate_draft  # 遅延 import で循環回避
    from comms.telegram_approval import send_approval_card

    db = get_db()
    drafted = 0
    failed = 0
    try:
        now = datetime.utcnow()
        offers = (
            db.query(OutboundOffer)
            .filter(
                OutboundOffer.status == "draft",
                OutboundOffer.draft_body == "",
                OutboundOffer.due_at <= now,
            )
            .order_by(OutboundOffer.due_at.asc())
            .limit(20)
            .all()
        )

        for offer in offers:
            try:
                # allowlist チェック
                if (
                    REPEAT_ENGINE_ALLOWLIST_BUYERS
                    and offer.buyer_username not in REPEAT_ENGINE_ALLOWLIST_BUYERS
                ):
                    offer.status = "suppressed"
                    offer.error_message = "buyer not in allowlist"
                    continue

                sale = None
                if offer.past_sale_record_id:
                    sale = (
                        db.query(SalesRecord)
                        .filter(SalesRecord.id == offer.past_sale_record_id)
                        .first()
                    )

                draft = generate_draft(
                    buyer_username=offer.buyer_username,
                    past_title=(sale.title if sale else ""),
                    past_category_tag=(sale.item_category_tag if sale else "other"),
                    delivered_at=(sale.delivered_at if sale else None),
                    feedback_comment=(sale.feedback_comment if sale else ""),
                )

                offer.draft_subject = draft.get("subject", "")[:256]
                offer.draft_body = draft.get("body", "")
                offer.draft_rationale = draft.get("rationale", "")
                flags = compliance_check(offer.draft_body)
                offer.compliance_flags_json = json.dumps(flags, ensure_ascii=False)
                offer.status = "awaiting_approval"
                db.commit()

                # Telegram 承認カードを送る（失敗しても DB 状態は維持）
                try:
                    asyncio.run(send_approval_card(offer.id))
                except Exception:
                    logger.exception(f"send_approval_card failed for offer={offer.id}")
                drafted += 1
            except Exception:
                logger.exception(f"draft generation failed for offer={offer.id}")
                offer.error_message = "draft_generation_failed"
                db.commit()
                failed += 1

        logger.info(
            f"draft_pending_post_feedback: drafted={drafted} failed={failed} "
            f"queue={len(offers)}"
        )
        return {"drafted": drafted, "failed": failed, "queue": len(offers)}
    except Exception:
        logger.exception("draft_pending_post_feedback failed")
        db.rollback()
        return {"error": True}
    finally:
        db.close()


# ── 承認後の送信 ────────────────────────────────────


def _today_sent_count(db: Session) -> int:
    today = datetime.utcnow().date()
    return (
        db.query(OutboundOffer)
        .filter(
            OutboundOffer.status == "sent",
            func.date(OutboundOffer.sent_at) == today,
        )
        .count()
    )


def dispatch_send(offer_id: int, approved_by: str = "telegram") -> dict:
    """approve された outbound_offer を eBay へ送信する。

    Phase 1 では Trading API send_buyer_message を直接呼ぶ。
    DRY_RUN=true の間は実送信しないが、status だけは sent に進めず draft_body を保持する。
    """
    db = get_db()
    try:
        offer = db.query(OutboundOffer).filter(OutboundOffer.id == offer_id).first()
        if offer is None:
            return {"error": "offer_not_found"}
        if offer.status not in ("awaiting_approval", "approved"):
            return {"error": f"bad_status:{offer.status}"}

        flags = json.loads(offer.compliance_flags_json or "[]")
        if has_block_flag(flags):
            offer.error_message = "blocked_by_compliance"
            db.commit()
            return {"error": "blocked_by_compliance", "flags": flags}

        if not offer.past_order_item_id:
            offer.status = "failed"
            offer.error_message = "no_item_id"
            db.commit()
            return {"error": "no_item_id"}

        # daily cap
        if _today_sent_count(db) >= REPEAT_ENGINE_DAILY_SEND_CAP:
            offer.error_message = "daily_cap_reached"
            db.commit()
            return {"error": "daily_cap_reached"}

        if REPEAT_ENGINE_DRY_RUN:
            offer.status = "sent"
            offer.approved_by = approved_by
            offer.approved_at = datetime.utcnow()
            offer.sent_at = datetime.utcnow()
            offer.error_message = "dry_run"
            db.commit()
            _record_audit_log(db, offer, success=True, dry_run=True)
            logger.info(f"dispatch_send DRY_RUN: offer={offer.id}")
            return {"sent": True, "dry_run": True}

        offer.status = "approved"
        offer.approved_by = approved_by
        offer.approved_at = datetime.utcnow()
        db.commit()

        from ebay_core.client import send_buyer_message  # 遅延 import

        result = send_buyer_message(
            item_id=offer.past_order_item_id,
            recipient_id=offer.buyer_username,
            body=offer.draft_body,
            subject=offer.draft_subject or "",
        )

        if result.get("success"):
            offer.status = "sent"
            offer.sent_at = datetime.utcnow()
            db.commit()
            _record_audit_log(db, offer, success=True)
            _bump_segment_contact(db, offer.buyer_username)
            logger.info(f"dispatch_send OK: offer={offer.id}")
            return {"sent": True}
        else:
            offer.status = "failed"
            offer.error_message = (result.get("error") or "send_failed")[:512]
            db.commit()
            _record_audit_log(db, offer, success=False, err=offer.error_message)
            logger.warning(
                f"dispatch_send FAILED: offer={offer.id} err={offer.error_message}"
            )
            return {"sent": False, "error": offer.error_message}
    except Exception as e:
        logger.exception(f"dispatch_send crashed for offer={offer_id}")
        db.rollback()
        return {"error": str(e)}
    finally:
        db.close()


def _record_audit_log(
    db: Session,
    offer: OutboundOffer,
    success: bool,
    dry_run: bool = False,
    err: str = "",
) -> None:
    """既存ダッシュボード互換のため AutoMessageLog にもミラー記録する。"""
    try:
        log = AutoMessageLog(
            rule_id=0,
            event_type="repeat_buyer_promotion",
            buyer_username=offer.buyer_username,
            item_id=offer.past_order_item_id,
            order_id="",
            message_body=(offer.draft_body or "")[:4000],
            is_repeat_buyer=1,
            success=1 if success else 0,
            error_message=("dry_run" if dry_run else (err or None)),
        )
        db.add(log)
        db.commit()
    except Exception:
        logger.exception("audit log mirror failed")
        db.rollback()


def _bump_segment_contact(db: Session, buyer: str) -> None:
    try:
        segs = db.query(BuyerSegment).filter(BuyerSegment.buyer_username == buyer).all()
        for seg in segs:
            seg.contact_count = (seg.contact_count or 0) + 1
            seg.last_contacted_at = datetime.utcnow()
        db.commit()
    except Exception:
        logger.exception("bump_segment_contact failed")
        db.rollback()


# ── Telegram 承認ハンドラ ─────────────────────────────


def handle_telegram_action(action: str, offer_id: int, cb: dict) -> dict:
    """Telegram callback_query から呼ばれる。action ∈ {approve, reject, edit}.

    cb には from.username / message.message_id などが入っている前提。
    """
    db = get_db()
    try:
        offer = db.query(OutboundOffer).filter(OutboundOffer.id == offer_id).first()
        if offer is None:
            return {"error": "offer_not_found"}

        user = (cb.get("from") or {}).get("username") or str(
            (cb.get("from") or {}).get("id", "")
        )

        if action == "reject":
            offer.status = "rejected"
            offer.approved_by = user
            offer.approved_at = datetime.utcnow()
            db.commit()
            return {"rejected": True, "offer_id": offer.id}

        if action == "approve":
            # status は in dispatch_send で進める
            db.close()
            return dispatch_send(offer_id, approved_by=f"telegram:{user}")

        if action == "edit":
            # 別途、次に届く非 callback テキストで draft_body 上書き
            offer.status = "awaiting_approval"
            db.commit()
            return {"edit_pending": True, "offer_id": offer.id}

        return {"error": f"unknown_action:{action}"}
    except Exception as e:
        logger.exception(f"handle_telegram_action crashed offer={offer_id}")
        db.rollback()
        return {"error": str(e)}
    finally:
        try:
            db.close()
        except Exception:
            pass


# ── opt-out ──────────────────────────────────────────


def opt_out_buyer(buyer_username: str, reason: str = "user_request") -> dict:
    """バイヤーを全 BuyerSegment / BuyerExclude に追加する。"""
    if not buyer_username:
        return {"error": "no_buyer"}
    db = get_db()
    try:
        for seg in (
            db.query(BuyerSegment)
            .filter(BuyerSegment.buyer_username == buyer_username)
            .all()
        ):
            seg.opt_out = 1

        if (
            not db.query(BuyerExclude)
            .filter(BuyerExclude.buyer_username == buyer_username)
            .first()
        ):
            db.add(BuyerExclude(buyer_username=buyer_username, reason=reason))

        # 飛行中の draft / awaiting_approval は suppressed に
        db.query(OutboundOffer).filter(
            OutboundOffer.buyer_username == buyer_username,
            OutboundOffer.status.in_(("draft", "awaiting_approval")),
        ).update({"status": "suppressed", "error_message": "opt_out"})

        db.commit()
        return {"opted_out": buyer_username}
    except Exception:
        logger.exception("opt_out_buyer failed")
        db.rollback()
        return {"error": True}
    finally:
        db.close()
