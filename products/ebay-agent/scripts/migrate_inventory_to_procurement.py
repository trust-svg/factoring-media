#!/usr/bin/env python3
"""inventory_items → procurements 一括移行スクリプト（一回限り）

実行: cd products/ebay-agent && python scripts/migrate_inventory_to_procurement.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import SessionLocal, InventoryItem, Procurement
from database.crud import add_procurement


def migrate() -> None:
    db = SessionLocal()
    try:
        items = db.query(InventoryItem).all()
        print(f"inventory_items 合計: {len(items)}件")

        # 既存 procurements の SKU セット（重複防止: procurements 優先）
        existing_skus: set[str] = {
            p.sku for p in db.query(Procurement).filter(Procurement.sku != "").all()
        }
        print(f"既存 procurements SKU数: {len(existing_skus)}")

        created = 0
        skipped_sku = 0
        skipped_dup = 0

        for item in items:
            # SKU が既に procurements にある → スキップ（procurements 優先）
            if item.sku and item.sku in existing_skus:
                skipped_sku += 1
                continue

            # タイトル + 価格 + 仕入先の完全一致 → スキップ
            dup = (
                db.query(Procurement)
                .filter(
                    Procurement.title == (item.title or ""),
                    Procurement.purchase_price_jpy == (item.purchase_price_jpy or 0),
                    Procurement.platform == (item.purchase_source or ""),
                )
                .first()
            )
            if dup:
                skipped_dup += 1
                continue

            kwargs: dict = {
                "sku": item.sku or "",
                "platform": item.purchase_source or "",
                "title": item.title or "",
                "url": item.purchase_url or "",
                "purchase_price_jpy": item.purchase_price_jpy or 0,
                "consumption_tax_jpy": item.consumption_tax_jpy or 0,
                "shipping_cost_jpy": item.shipping_cost_jpy or 0,
                "seller_id": item.seller_id or "",
                "seller_url": item.seller_url or "",
                "screenshot_path": item.screenshot_path or "",
                "quantity": item.quantity or 1,
                "category": "",  # 未分類（後で手動設定）
                "notes": item.notes or "",
                "status": "purchased",
            }
            if item.purchase_date:
                kwargs["purchase_date"] = item.purchase_date

            add_procurement(db, **kwargs)

            if item.sku:
                existing_skus.add(item.sku)
            created += 1

        print(
            f"完了: 作成 {created}件 / SKU重複スキップ {skipped_sku}件 / 完全重複スキップ {skipped_dup}件"
        )
        print(
            f"category='': {created}件が未設定（古物台帳エクスポート前に手動設定推奨）"
        )
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
