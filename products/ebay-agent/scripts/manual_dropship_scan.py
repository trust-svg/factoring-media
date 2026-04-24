"""手動で無在庫パイプラインを走らせる診断スクリプト

使い方:
    docker compose exec ebay-agent python scripts/manual_dropship_scan.py

オプション環境変数:
    RESET_HOT=1    旧 hot_expensive_items をクリアしてから再スキャン
"""
import asyncio
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

from database.models import get_db, HotExpensiveItem
from research.hot_expensive import scan_top_categories
from sourcing.reverse_match import find_jp_candidates
from comms.dropship_notify import send_dropship_digest


def main():
    db = get_db()

    if os.getenv("RESET_HOT") == "1":
        deleted = db.query(HotExpensiveItem).delete()
        db.commit()
        print(f"=== 旧hot_items削除: {deleted}件 ===")

    print("=== Step1: eBayスキャン ===")
    hot = scan_top_categories(db)
    print(f"hot_expensive_items: {len(hot)}件")

    print("=== Step2: 国内逆検索（品質ガード適用） ===")
    cands = asyncio.run(find_jp_candidates(db))
    print(f"dropship_candidates: {len(cands)}件")

    print("=== Step3: Telegram ===")
    result = asyncio.run(send_dropship_digest(db))
    print(f"Telegram: {result}")


if __name__ == "__main__":
    main()
