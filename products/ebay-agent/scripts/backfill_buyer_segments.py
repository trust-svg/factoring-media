"""sales_records から item_category_tag をバックフィル → buyer_segments を初期構築。

使い方:
    python scripts/backfill_buyer_segments.py --dry-run
    python scripts/backfill_buyer_segments.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.models import SalesRecord, get_db, init_db  # noqa: E402
from chat.repeat_engine import (  # noqa: E402
    classify_sale,
    rebuild_buyer_segments,
    seed_default_rules,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # スキーマ確実化（既に init_db 済みなら冪等）
    init_db()

    db = get_db()
    try:
        seeded = seed_default_rules(db)
        print(f"Seeded default category rules: {seeded}")

        sales = (
            db.query(SalesRecord)
            .filter(SalesRecord.buyer_name != "")
            .order_by(SalesRecord.sold_at.desc())
            .all()
        )
        print(f"Sales records scanned: {len(sales)}")

        classified = 0
        for sale in sales:
            if sale.item_category_tag:
                continue
            tag = classify_sale(db, sale)
            if args.dry_run:
                print(
                    f"[dry-run] {sale.id} buyer={sale.buyer_name} "
                    f"sku={sale.sku} → {tag}"
                )
            else:
                sale.item_category_tag = tag
            classified += 1
        if not args.dry_run:
            db.commit()
        print(f"Classified: {classified} (dry_run={args.dry_run})")
    finally:
        db.close()

    if args.dry_run:
        print("Skipping rebuild_buyer_segments (dry-run)")
        return 0

    # buyer_segments 再構築は engine の同名関数を呼ぶ（REPEAT_ENGINE_ENABLED ガード経由）
    import os

    os.environ.setdefault("REPEAT_ENGINE_ENABLED", "true")
    # 注意: この関数は config 値を再読み込みしないので、上書きは別プロセスで効く
    # ローカル backfill 用途では一時的に true で呼ぶことを想定。
    import importlib
    import chat.repeat_engine as eng
    import config as cfg

    importlib.reload(cfg)
    importlib.reload(eng)
    result = eng.rebuild_buyer_segments()
    print(f"rebuild_buyer_segments: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
