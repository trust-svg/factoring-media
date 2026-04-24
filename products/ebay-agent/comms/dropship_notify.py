"""無在庫出品パイプラインの Telegram 通知

日次で dropship_candidates の上位候補を Telegram に送信する。
送信後は DropshipCandidate.status を 'pending' のまま保持し、
ユーザーが eBay URL / JP URL を確認して /approve するまで待機。

既存 @bmanager_trustlink_bot（Chat ID: 323107833）を流用する想定。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import (
    DROPSHIP_DIGEST_TOP_N,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)
from database.models import DropshipCandidate


logger = logging.getLogger(__name__)


PLATFORM_LABELS = {
    "yahoo_auction": "ヤフオク",
    "mercari": "メルカリ",
    "paypay_flea": "PayPayフリマ",
    "yahoo_fleamarket": "Yahooフリマ",
    "rakuma": "ラクマ",
    "surugaya": "駿河屋",
    "offmall": "オフモール",
    "hardoff": "ハードオフ",
}


async def send_telegram(text: str, disable_preview: bool = True) -> bool:
    """Telegram sendMessage ラッパー。成功なら True。"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram 未設定 — 通知スキップ")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": disable_preview,
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=15)
        if resp.status_code != 200:
            logger.error(f"Telegram API error: {resp.status_code} {resp.text[:300]}")
            return False
        return True
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


def _format_candidate_line(idx: int, c: DropshipCandidate) -> str:
    platform_label = PLATFORM_LABELS.get(c.jp_platform, c.jp_platform or "?")
    title = (c.jp_title or "")[:70]
    return (
        f"<b>#{idx}</b> {title}\n"
        f"  eBay想定: ${c.ebay_target_price_usd:.0f} | "
        f"{platform_label}: ¥{c.jp_price_jpy:,}\n"
        f"  利益 ${c.projected_profit_usd:.0f} "
        f"(マージン {c.projected_margin_pct:.1f}%)\n"
        f"  国内: {c.jp_url}\n"
        f"  候補ID: <code>{c.id}</code>"
    )


async def send_dropship_digest(db: Session, limit: int = DROPSHIP_DIGEST_TOP_N) -> dict:
    """過去24時間の pending 候補を利益順に上位Nを Telegram 送信。"""
    cutoff = datetime.utcnow() - timedelta(hours=24)
    rows = list(db.execute(
        select(DropshipCandidate)
        .where(
            DropshipCandidate.status == "pending",
            DropshipCandidate.created_at >= cutoff,
        )
        .order_by(
            DropshipCandidate.projected_profit_usd.desc(),
            DropshipCandidate.projected_margin_pct.desc(),
        )
        .limit(limit)
    ).scalars().all())

    if not rows:
        msg = "📦 <b>無在庫候補スキャン完了</b>\n\n今日の新規候補はありませんでした。"
        sent = await send_telegram(msg)
        return {"sent": sent, "count": 0}

    total_profit = sum(r.projected_profit_usd for r in rows)
    lines = [
        f"📦 <b>無在庫出品候補（{len(rows)}件）</b>",
        f"想定利益合計: ${total_profit:.0f}",
        "",
    ]
    for idx, c in enumerate(rows, 1):
        lines.append(_format_candidate_line(idx, c))
        lines.append("")  # 空行で区切り

    lines.append(
        "承認するには候補IDを指定して "
        "<code>/approve &lt;ID&gt;</code> または Agent Hub の "
        "<code>POST /api/dropship/approve</code> を実行してください。"
    )

    sent = await send_telegram("\n".join(lines))
    # 通知送信フラグはテーブル設計通り telegram_message_id に保存できるが、
    # sendMessage のレスポンスから取得する実装は /approve 実装時に追加する。
    return {"sent": sent, "count": len(rows), "profit_total_usd": round(total_profit, 2)}
