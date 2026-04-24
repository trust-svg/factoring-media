"""死に筒リフレッシュ（S2施策）

180日間無販売の出品に対して、タイトル再生成＋$1値下げで
"Recently Modified" シグナルを発火させ、Cassiniランキング回復を狙う。

設計方針:
- Reviseのみ（ItemIDを維持 → e-ship同期不要、SOLD履歴保持）
- 日中06:00-23:00 JST に 20-30分ごとに 1-2件で分散実行
- タイトル品質ガード: モデル番号・ブランド名の保持を必須化
- 全変更をlisting_refresh_backupsに保存 → ロールバック可能
- ドライラン → 確認 → 自動実行ON の段階的展開
"""
from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from database.models import (
    Listing,
    ListingRefreshBackup,
    ListingRefreshRun,
    SalesRecord,
    get_db,
)

logger = logging.getLogger("refresh")

# ── 定数 ──────────────────────────────────────────────────
TITLE_MAX = 80                 # eBayタイトル上限
PRICE_DROP_USD = 1.0           # Cassiniシグナル用の微値下げ
DEAD_THRESHOLD_DAYS = 180      # 死に筒判定: 最終販売からN日
MIN_REFRESH_GAP_DAYS = 60      # 最低でも N日経ってから再Refresh
MIN_TOKEN_OVERLAP = 0.7        # 新タイトルは元タイトルのトークン70%以上を保持
MAX_TITLE_DIFF_RATIO = 0.4     # 文字変更率40%以内
DEFAULT_DAILY_TARGET = 30
DEFAULT_HOUR_START = 6
DEFAULT_HOUR_END = 23
SKIP_PROB = 0.15               # スロット実行のランダムスキップ率


# ── 型番・ブランド抽出 ─────────────────────────────────────
MODEL_NUM_RE = re.compile(r"\b[A-Z0-9]{2,}-?[A-Z0-9]+\b|\b[A-Z]{2,}\d+[A-Z0-9]*\b")

COMMON_BRANDS = {
    "TASCAM", "Technics", "Mamiya", "Yamaha", "YAMAHA", "Korg", "KORG",
    "Roland", "Pioneer", "Nakamichi", "Micro", "Seiki", "Sony", "SONY",
    "Canon", "Nikon", "Rolleicord", "Allen", "Heath", "Denon", "Bandai",
    "Xiaomi", "Accuphase", "Marantz", "Fender", "Gibson",
}


def _tokens(title: str) -> set[str]:
    """タイトルを単語トークン化（lowercase、記号除去）"""
    return {t.lower() for t in re.findall(r"[A-Za-z0-9\-]+", title) if len(t) >= 2}


def _extract_protected_tokens(title: str) -> dict:
    """タイトルから保持必須トークン（ブランド・モデル番号）を抽出"""
    model_nums = set(MODEL_NUM_RE.findall(title))
    brands = {w for w in re.findall(r"[A-Za-z]+", title) if w in COMMON_BRANDS}
    return {"models": model_nums, "brands": brands}


# ── 品質ガード ────────────────────────────────────────────
@dataclass
class QualityCheck:
    passed: bool
    reason: str
    details: dict


def validate_new_title(old_title: str, new_title: str) -> QualityCheck:
    """新タイトルが品質基準を満たすか検証"""
    details: dict = {
        "old_len": len(old_title),
        "new_len": len(new_title),
    }

    if not new_title or not new_title.strip():
        return QualityCheck(False, "empty_title", details)

    if len(new_title) > TITLE_MAX:
        return QualityCheck(False, f"exceeds_max_{TITLE_MAX}", details)

    if len(new_title) < 30:
        return QualityCheck(False, "too_short", details)

    protected = _extract_protected_tokens(old_title)
    new_upper = new_title.upper()

    # モデル番号保持チェック
    missing_models = [m for m in protected["models"] if m.upper() not in new_upper]
    details["missing_models"] = missing_models
    if missing_models:
        return QualityCheck(False, f"missing_model_numbers:{missing_models}", details)

    # ブランド保持チェック（大文字小文字無視）
    missing_brands = [b for b in protected["brands"] if b.upper() not in new_upper]
    details["missing_brands"] = missing_brands
    if missing_brands:
        return QualityCheck(False, f"missing_brands:{missing_brands}", details)

    # トークン重複率（SEO用キーワード保持）
    old_tokens = _tokens(old_title)
    new_tokens = _tokens(new_title)
    if old_tokens:
        overlap = len(old_tokens & new_tokens) / len(old_tokens)
        details["token_overlap"] = round(overlap, 3)
        if overlap < MIN_TOKEN_OVERLAP:
            return QualityCheck(False, f"token_overlap_{overlap:.2f}_<_{MIN_TOKEN_OVERLAP}", details)

    # 大幅な文字変更はCassini ranking resetのリスク → 抑制
    diff_ratio = _char_diff_ratio(old_title, new_title)
    details["char_diff_ratio"] = round(diff_ratio, 3)
    if diff_ratio > MAX_TITLE_DIFF_RATIO:
        return QualityCheck(False, f"char_diff_{diff_ratio:.2f}_>_{MAX_TITLE_DIFF_RATIO}", details)

    return QualityCheck(True, "ok", details)


def _char_diff_ratio(a: str, b: str) -> float:
    """2つのタイトルの文字列類似度から差分率を計算（0.0=同一, 1.0=完全別物）"""
    import difflib
    ratio = difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()
    return 1.0 - ratio


# ── 死に筒SKUの抽出 ───────────────────────────────────────
def find_dead_listings(
    db: Session,
    threshold_days: int = DEAD_THRESHOLD_DAYS,
    exclude_recently_refreshed: bool = True,
    limit: int = 500,
) -> list[Listing]:
    """
    死に筒SKU抽出条件:
      - quantity = 1 （在庫あり）
      - 過去 threshold_days 日間に売上なし
      - (任意) 直近 MIN_REFRESH_GAP_DAYS 日以内にRefresh済みは除外
    """
    cutoff = datetime.utcnow() - timedelta(days=threshold_days)

    # 過去180日に売上があるSKUを除外
    recently_sold = select(SalesRecord.sku).where(SalesRecord.sold_at >= cutoff)
    # 無在庫出品（dropship_ebay_reverse）は在庫リアリティがないためリフレッシュ対象外
    q = select(Listing).where(
        Listing.quantity == 1,
        Listing.source_type.in_(["stocked", "dropship_jp"]),
        ~Listing.sku.in_(recently_sold),
    )

    if exclude_recently_refreshed:
        refresh_cutoff = datetime.utcnow() - timedelta(days=MIN_REFRESH_GAP_DAYS)
        recently_refreshed = select(ListingRefreshBackup.sku).where(
            and_(
                ListingRefreshBackup.applied_at >= refresh_cutoff,
                ListingRefreshBackup.status == "applied",
            )
        )
        q = q.where(~Listing.sku.in_(recently_refreshed))

    q = q.order_by(Listing.price_usd.desc()).limit(limit)
    return list(db.execute(q).scalars().all())


# ── タイトル再生成（AI） ──────────────────────────────────
async def regenerate_title(
    old_title: str,
    current_specifics: Optional[dict] = None,
    category: str = "",
) -> str:
    """
    既存タイトルをベースに、品質ガードに通る形でSEO最適化した新タイトルを生成。

    制約:
      - ブランド名・モデル番号は完全保持
      - eBayタイトル80字以内
      - 英語表記、キーワード密度維持
      - 微調整のみ（語順入れ替え・副詞追加・コンディション追加程度）
    """
    import anthropic

    client = anthropic.Anthropic()
    protected = _extract_protected_tokens(old_title)
    specifics_str = json.dumps(current_specifics or {}, ensure_ascii=False)[:500]

    system = (
        "You are an eBay SEO copywriter for a Japan-export vintage audio store. "
        "Your job: take an EXISTING live listing title and produce a REFRESHED version "
        "that triggers Cassini's 'recently modified' boost without losing SEO equity.\n\n"
        "HARD CONSTRAINTS:\n"
        "1. Max 80 characters (eBay limit).\n"
        "2. Preserve ALL model numbers and brand names VERBATIM.\n"
        "3. Keep at least 70% of the original meaningful tokens.\n"
        "4. Character diff ratio vs original must be ≤ 40% — small refinements only.\n"
        "5. Output the NEW TITLE ONLY. No quotes, no explanation.\n\n"
        "REFRESH TACTICS (pick 1-2, not all):\n"
        "- Add/swap one high-intent keyword (Tested, Working, Excellent, Rare, Vintage, From Japan).\n"
        "- Reorder for better keyword-front loading.\n"
        "- Expand abbreviation (e.g., 'MK2' → 'MKII').\n"
        "- Add condition descriptor if missing.\n"
        "- Add 'Free Shipping' / 'Fast Ship' if under 80 chars.\n"
        "NEVER: translate, remove brand, remove model#, add emoji, add unrelated keywords."
    )

    user = (
        f"ORIGINAL TITLE ({len(old_title)} chars):\n{old_title}\n\n"
        f"MUST PRESERVE: brands={list(protected['brands'])}, models={list(protected['models'])}\n"
        f"CATEGORY: {category or 'unknown'}\n"
        f"ITEM SPECIFICS: {specifics_str}\n\n"
        f"Output the refreshed title only."
    )

    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    new_title = resp.content[0].text.strip().strip('"').strip("'")
    # 一行に強制
    new_title = new_title.split("\n")[0].strip()
    return new_title[:TITLE_MAX]


# ── ドライラン ────────────────────────────────────────────
async def dry_run_refresh(
    db: Session,
    sample_size: int = 10,
) -> list[dict]:
    """サンプルSKUで新タイトルを生成して品質ガード結果を返す（API更新なし）"""
    candidates = find_dead_listings(db, limit=sample_size * 3)
    if not candidates:
        return []
    sample = random.sample(candidates, min(sample_size, len(candidates)))
    results: list[dict] = []
    for listing in sample:
        try:
            specifics = json.loads(listing.item_specifics_json or "{}")
        except Exception:
            specifics = {}
        try:
            new_title = await regenerate_title(
                listing.title,
                current_specifics=specifics,
                category=listing.category_name,
            )
            check = validate_new_title(listing.title, new_title)
            results.append({
                "sku": listing.sku,
                "old_title": listing.title,
                "new_title": new_title,
                "old_price_usd": listing.price_usd,
                "new_price_usd": round(listing.price_usd - PRICE_DROP_USD, 2),
                "passed": check.passed,
                "reason": check.reason,
                "details": check.details,
            })
        except Exception as e:
            logger.exception(f"dry-run失敗 sku={listing.sku}")
            results.append({
                "sku": listing.sku,
                "old_title": listing.title,
                "error": str(e)[:200],
                "passed": False,
            })
    return results


# ── 実Revise実行 ──────────────────────────────────────────
def _log_run(
    db: Session, sku: str, outcome: str, backup_id: Optional[int] = None, note: str = ""
) -> None:
    now = datetime.utcnow()
    jst_hour = (now.hour + 9) % 24
    db.add(ListingRefreshRun(
        scheduled_date=now.strftime("%Y-%m-%d"),
        hour_jst=jst_hour,
        sku=sku,
        backup_id=backup_id,
        outcome=outcome,
        note=note[:500] if note else None,
    ))
    db.commit()


async def refresh_single(
    db: Session,
    listing: Listing,
    dry_run: bool = False,
) -> dict:
    """1件のリスティングをRefresh（新タイトル生成 → 品質検証 → Revise）"""
    try:
        specifics = json.loads(listing.item_specifics_json or "{}")
    except Exception:
        specifics = {}

    try:
        new_title = await regenerate_title(
            listing.title,
            current_specifics=specifics,
            category=listing.category_name,
        )
    except Exception as e:
        logger.exception(f"タイトル生成失敗 sku={listing.sku}")
        _log_run(db, listing.sku, "error", note=f"title_gen_failed: {e}")
        return {"sku": listing.sku, "success": False, "error": f"title_gen: {e}"}

    check = validate_new_title(listing.title, new_title)
    new_price = round(listing.price_usd - PRICE_DROP_USD, 2)
    if new_price < 1.0:
        new_price = listing.price_usd  # 安すぎる場合は値下げしない

    backup = ListingRefreshBackup(
        sku=listing.sku,
        listing_id=listing.listing_id,
        action="revise",
        old_title=listing.title,
        new_title=new_title,
        old_price_usd=listing.price_usd,
        new_price_usd=new_price,
        old_item_specifics_json=listing.item_specifics_json or "{}",
        new_item_specifics_json=listing.item_specifics_json or "{}",
        quality_checks_json=json.dumps(check.details),
        status="dry_run" if dry_run else ("pending" if check.passed else "skipped"),
        error_message=None if check.passed else check.reason,
    )
    db.add(backup)
    db.commit()
    db.refresh(backup)

    if not check.passed:
        _log_run(db, listing.sku, "skipped_quality", backup.id, check.reason)
        return {
            "sku": listing.sku, "success": False, "skipped": True,
            "reason": check.reason, "backup_id": backup.id,
        }

    if dry_run:
        _log_run(db, listing.sku, "dry_run", backup.id)
        return {
            "sku": listing.sku, "success": True, "dry_run": True,
            "old_title": listing.title, "new_title": new_title,
            "old_price": listing.price_usd, "new_price": new_price,
            "backup_id": backup.id,
        }

    # 実更新
    from ebay_core.client import update_listing
    try:
        result = update_listing(listing.sku, {
            "title": new_title,
            "price_usd": new_price,
        })
        if not result.get("success"):
            backup.status = "failed"
            backup.error_message = result.get("error", "unknown")[:500]
            db.commit()
            _log_run(db, listing.sku, "error", backup.id, backup.error_message)
            return {"sku": listing.sku, "success": False, "error": result.get("error"), "backup_id": backup.id}

        # DB側を更新
        listing.title = new_title
        listing.price_usd = new_price
        backup.status = "applied"
        backup.applied_at = datetime.utcnow()
        db.commit()
        _log_run(db, listing.sku, "applied", backup.id)
        return {
            "sku": listing.sku, "success": True, "backup_id": backup.id,
            "changes": result.get("changes", []),
        }
    except Exception as e:
        logger.exception(f"Revise API失敗 sku={listing.sku}")
        backup.status = "failed"
        backup.error_message = str(e)[:500]
        db.commit()
        _log_run(db, listing.sku, "error", backup.id, str(e))
        return {"sku": listing.sku, "success": False, "error": str(e), "backup_id": backup.id}


# ── スケジューラ呼び出し用（スロット実行） ─────────────────
def _today_applied_count(db: Session) -> int:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    return db.query(ListingRefreshRun).filter(
        ListingRefreshRun.scheduled_date == today,
        ListingRefreshRun.outcome == "applied",
    ).count()


def is_in_window(hour_jst: Optional[int] = None) -> bool:
    if hour_jst is None:
        hour_jst = (datetime.utcnow().hour + 9) % 24
    return DEFAULT_HOUR_START <= hour_jst <= DEFAULT_HOUR_END


async def run_refresh_slot(
    daily_target: int = DEFAULT_DAILY_TARGET,
    items_per_slot: tuple[int, int] = (1, 2),
    skip_prob: float = SKIP_PROB,
    dry_run: bool = False,
) -> dict:
    """
    APSchedulerから20-30分おきに呼ばれる1スロット実行。

      - JST時間帯チェック（窓外ならスキップ）
      - ランダムスキップで機械的パターン回避
      - 日次上限到達時は停止
      - 1-2件を処理
    """
    now = datetime.utcnow()
    hour_jst = (now.hour + 9) % 24
    if not is_in_window(hour_jst):
        return {"skipped": True, "reason": "outside_window", "hour_jst": hour_jst}

    if random.random() < skip_prob:
        return {"skipped": True, "reason": "random_skip"}

    db = get_db()
    try:
        already = _today_applied_count(db)
        if already >= daily_target:
            return {"skipped": True, "reason": "daily_cap_reached", "already": already}

        remaining_budget = daily_target - already
        n_pick = min(random.randint(*items_per_slot), remaining_budget)

        candidates = find_dead_listings(db, limit=50)
        if not candidates:
            return {"skipped": True, "reason": "no_candidates"}

        picks = random.sample(candidates, min(n_pick, len(candidates)))
        results = []
        for listing in picks:
            result = await refresh_single(db, listing, dry_run=dry_run)
            results.append(result)

        return {
            "skipped": False,
            "hour_jst": hour_jst,
            "processed": len(results),
            "daily_applied": already + sum(1 for r in results if r.get("success") and not r.get("dry_run")),
            "results": results,
        }
    finally:
        db.close()


# ── ロールバック ──────────────────────────────────────────
def rollback(db: Session, backup_id: int) -> dict:
    """指定バックアップIDの変更を元に戻す"""
    backup = db.get(ListingRefreshBackup, backup_id)
    if not backup:
        return {"success": False, "error": "backup not found"}
    if backup.status != "applied":
        return {"success": False, "error": f"cannot rollback status={backup.status}"}

    from ebay_core.client import update_listing
    result = update_listing(backup.sku, {
        "title": backup.old_title,
        "price_usd": backup.old_price_usd,
    })
    if not result.get("success"):
        return {"success": False, "error": result.get("error")}

    listing = db.get(Listing, backup.sku)
    if listing:
        listing.title = backup.old_title
        listing.price_usd = backup.old_price_usd
    backup.status = "rolled_back"
    backup.rolled_back_at = datetime.utcnow()
    db.commit()
    return {"success": True, "sku": backup.sku, "restored_title": backup.old_title}
