#!/usr/bin/env python3
"""InventoryItem → Procurement バックフィル（eBay連携・管理フィールド）

実行: docker exec ebay-agent python3 /app/scripts/backfill_procurement_ebay_fields.py
"""

import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import SessionLocal, InventoryItem, Procurement

db = SessionLocal()
try:
    procs = db.query(Procurement).filter(Procurement.sku != "").all()
    print(f"SKUあり procurement: {len(procs)}件")

    updated = 0
    skipped = 0
    for proc in procs:
        inv = db.query(InventoryItem).filter(InventoryItem.sku == proc.sku).first()
        if not inv:
            skipped += 1
            continue
        changed = False
        if not proc.ebay_item_id and inv.ebay_item_id:
            proc.ebay_item_id = inv.ebay_item_id
            changed = True
        if not proc.ebay_order_id and inv.ebay_order_id:
            proc.ebay_order_id = inv.ebay_order_id
            changed = True
        if not proc.ebay_price_usd and inv.ebay_price_usd:
            proc.ebay_price_usd = inv.ebay_price_usd
            changed = True
        if not proc.stock_number and inv.stock_number:
            proc.stock_number = inv.stock_number
            changed = True
        if not proc.location and inv.location:
            proc.location = inv.location
            changed = True
        if not proc.sold_at and inv.sold_at:
            proc.sold_at = inv.sold_at
            changed = True
        if not proc.listed_at and inv.listed_at:
            proc.listed_at = inv.listed_at
            changed = True
        if not proc.shipped_at and inv.shipped_at:
            proc.shipped_at = inv.shipped_at
            changed = True
        if changed:
            updated += 1

    db.commit()
    print(f"完了: 更新 {updated}件 / スキップ（InventoryItem未対応） {skipped}件")
finally:
    db.close()
