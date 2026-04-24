"""手動で無在庫パイプラインを走らせる診断スクリプト

使い方:
    docker compose exec -e PYTHONPATH=/app ebay-agent python scripts/manual_dropship_scan.py

オプション環境変数:
    RESET_HOT=1         旧 hot_expensive_items + dropship_candidates をクリア
    SKIP_TELEGRAM=1     Telegram送信をスキップ（品質確認のみ）
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

from database.models import DropshipCandidate, HotExpensiveItem, get_db
from research.hot_expensive import scan_top_categories
from sourcing.reverse_match import find_jp_candidates
from comms.dropship_notify import send_dropship_digest


def main():
    db = get_db()

    if os.getenv("RESET_HOT") == "1":
        hot_del = db.query(HotExpensiveItem).delete()
        cand_del = db.query(DropshipCandidate).delete()
        db.commit()
        print(
            f"=== RESET: hot_items削除={hot_del}件 / "
            f"dropship_candidates削除={cand_del}件 ==="
        )

    print("=== Step1: eBayスキャン ===")
    hot = scan_top_categories(db)
    print(f"hot_expensive_items: {len(hot)}件")

    print("=== Step2: 国内逆検索（品質ガード適用） ===")
    cands = asyncio.run(find_jp_candidates(db))
    print(f"dropship_candidates: {len(cands)}件")
    if cands:
        print("=== 採用候補一覧 ===")
        for c in cands[:10]:
            print(
                f"  [{c.jp_platform}] ¥{c.jp_price_jpy:,} "
                f"→ ${c.ebay_target_price_usd:.0f} "
                f"(利益 ${c.projected_profit_usd:.0f} / "
                f"{c.projected_margin_pct:.1f}% / "
                f"score={c.match_score:.1f})"
            )
            print(f"    {c.jp_title[:80]}")

    if os.getenv("SKIP_TELEGRAM") == "1":
        print("=== Step3: Telegram スキップ (SKIP_TELEGRAM=1) ===")
    else:
        print("=== Step3: Telegram ===")
        result = asyncio.run(send_dropship_digest(db))
        print(f"Telegram: {result}")


if __name__ == "__main__":
    main()
