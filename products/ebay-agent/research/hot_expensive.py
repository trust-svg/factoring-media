"""eBay 高額売れ筋検出（無在庫出品の候補発掘）

Browse API で指定クエリを走査し、$1500+ の売れ筋候補を
hot_expensive_items テーブルに格納する。

単品高額商品は multi-quantity 出品が少ないため soldQuantity は
低くなりがち。補助指標として active listing 数と中央値価格も使う。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import HotExpensiveItem, get_db
from ebay_core.client import search_ebay_discover


# クエリ設計方針:
#   - 型番 or 具体モデル名を必ず含める（単語2つ以上）
#   - 「vintage」「antique」等の形容詞単独クエリは曖昧すぎるため禁止
#   - 1ブランド1クエリに寄せすぎず、型番/モデルで分散させる
DEFAULT_QUERIES: list[dict] = [
    # Vintage Audio — アンプ/プリ/カセットデッキ等（型番入り）
    {"query": "accuphase E-305 amplifier", "category": "Vintage Audio"},
    {"query": "accuphase C-280 preamplifier", "category": "Vintage Audio"},
    {"query": "luxman L-570 amplifier", "category": "Vintage Audio"},
    {"query": "luxman CL-360 tube preamp", "category": "Vintage Audio"},
    {"query": "nakamichi dragon cassette deck", "category": "Vintage Audio"},
    {"query": "nakamichi 1000ZXL", "category": "Vintage Audio"},
    {"query": "mcintosh MC275 tube amplifier", "category": "Vintage Audio"},
    {"query": "technics SP-10 MK2 turntable", "category": "Vintage Audio"},
    {"query": "marantz 2270 receiver", "category": "Vintage Audio"},
    # Synthesizer（型番必須）
    {"query": "roland jupiter-8 synthesizer", "category": "Synthesizer"},
    {"query": "roland jp-8080", "category": "Synthesizer"},
    {"query": "korg ms-20 synthesizer", "category": "Synthesizer"},
    {"query": "yamaha dx7 synthesizer", "category": "Synthesizer"},
    {"query": "moog minimoog model D", "category": "Synthesizer"},
    # Vintage Camera（型番入り）
    {"query": "mamiya rz67 pro ii", "category": "Vintage Camera"},
    {"query": "hasselblad 500cm camera", "category": "Vintage Camera"},
    {"query": "leica m6 ttl", "category": "Vintage Camera"},
    {"query": "nikon f3 titanium", "category": "Vintage Camera"},
    # 日本関連（カテゴリ自体が狭いので vintage/antique 許容）
    {"query": "japanese edo samurai armor yoroi kabuto", "category": "Samurai Armor"},
    {"query": "japanese samurai kabuto helmet antique", "category": "Samurai Armor"},
    {"query": "japanese katana antique sword signed", "category": "Japanese Sword"},
    # Vintage Watch（型番必須 — "seiko vintage" だけだと誤マッチ多数）
    {"query": "casio G-SHOCK MRG-B2000 titanium", "category": "Vintage Watch"},
    {"query": "grand seiko SBGA spring drive", "category": "Vintage Watch"},
    {"query": "grand seiko SBGJ hi-beat", "category": "Vintage Watch"},
]


def _median_price(items: list[dict]) -> float:
    prices = [it["price"] for it in items if it.get("price", 0) > 0]
    return float(median(prices)) if prices else 0.0


def scan_query(
    query: str,
    category: str = "",
    category_id: str = "",
    price_min: float = 1500.0,
    price_max: float = 5000.0,
    limit: int = 50,
) -> Optional[dict]:
    """1クエリをスキャンして集計データを返す。候補なしなら None。"""
    result = search_ebay_discover(
        query=query,
        limit=limit,
        category_id=category_id,
        price_min=price_min,
        price_max=price_max,
    )
    items = result.get("items", [])
    total = result.get("total", 0)

    if not items:
        return None

    med_price = _median_price(items)
    total_sold = sum(it.get("sold_quantity", 0) for it in items)

    items_sorted = sorted(
        items,
        key=lambda x: (-x.get("sold_quantity", 0), x.get("price", 0)),
    )
    sample = items_sorted[0]
    prices = [it["price"] for it in items if it.get("price", 0) > 0]

    return {
        "title": sample.get("title", "")[:500],
        "query": query,
        "category": category,
        "category_id": category_id or sample.get("category_id", ""),
        "median_price_usd": round(med_price, 2),
        "min_price_usd": float(min(prices)) if prices else 0.0,
        "max_price_usd": float(max(prices)) if prices else 0.0,
        "sold_qty_30d": total_sold,
        "active_count": total,
        "sample_listing_id": sample.get("item_id", ""),
        "sample_url": sample.get("item_url", ""),
        "image_url": sample.get("image_url", ""),
    }


def scan_top_categories(
    db: Session,
    queries: Iterable[dict] = DEFAULT_QUERIES,
    price_min: float = 1500.0,
    price_max: float = 5000.0,
    dedupe_days: int = 7,
) -> list[HotExpensiveItem]:
    """設定リストをスキャンしてDBに保存。dedupe_days 以内に同クエリ記録があれば更新。"""
    saved: list[HotExpensiveItem] = []
    cutoff = datetime.utcnow() - timedelta(days=dedupe_days)

    for q in queries:
        row_data = scan_query(
            query=q.get("query", ""),
            category=q.get("category", ""),
            category_id=q.get("category_id", ""),
            price_min=price_min,
            price_max=price_max,
        )
        if not row_data:
            continue

        existing = db.execute(
            select(HotExpensiveItem).where(
                HotExpensiveItem.query == row_data["query"],
                HotExpensiveItem.discovered_at >= cutoff,
            ).order_by(HotExpensiveItem.discovered_at.desc())
        ).scalars().first()

        if existing:
            for k, v in row_data.items():
                setattr(existing, k, v)
            existing.discovered_at = datetime.utcnow()
            saved.append(existing)
        else:
            item = HotExpensiveItem(**row_data)
            db.add(item)
            saved.append(item)

    db.commit()
    return saved


def list_recent_hot(db: Session, days: int = 14, limit: int = 50) -> list[HotExpensiveItem]:
    """直近 N 日の新規発見候補を、sold + active で並べて返す。"""
    cutoff = datetime.utcnow() - timedelta(days=days)
    return list(db.execute(
        select(HotExpensiveItem)
        .where(HotExpensiveItem.discovered_at >= cutoff, HotExpensiveItem.status == "new")
        .order_by(
            HotExpensiveItem.sold_qty_30d.desc(),
            HotExpensiveItem.active_count.desc(),
        )
        .limit(limit)
    ).scalars().all())


if __name__ == "__main__":
    db = get_db()
    results = scan_top_categories(db)
    print(f"スキャン完了: {len(results)}候補")
    for r in results[:20]:
        print(
            f"  [{r.category}] {r.query} — "
            f"median ${r.median_price_usd:.0f} "
            f"× {r.active_count} active, "
            f"sold_qty={r.sold_qty_30d}"
        )
