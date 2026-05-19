"""既存の補完SSファイル名を撮影日→取引日にリネームしてDBも更新する（一回限り）

実行: VPS上で cd /app && python3 scripts/rename_ss_to_purchase_date.py
"""

import os
import re
from pathlib import Path
from database.models import SessionLocal, Procurement

db = SessionLocal()

renamed = skipped = errors = 0

procs = (
    db.query(Procurement)
    .filter(Procurement.screenshot_path.like("/app/screenshots%"))
    .all()
)

print(f"対象: {len(procs)}件")

for proc in procs:
    old_path = Path(proc.screenshot_path)
    if not old_path.exists():
        print(f"  [skip] id={proc.id} ファイルなし: {old_path}")
        skipped += 1
        continue

    # purchase_date があれば取引日、なければスキップ
    if not proc.purchase_date:
        print(f"  [skip] id={proc.id} purchase_date なし")
        skipped += 1
        continue

    date_str = proc.purchase_date.strftime("%Y%m%d")
    year = proc.purchase_date.strftime("%Y")
    platform = (proc.platform or "other").replace("/", "_").replace(" ", "_")
    safe = "".join(
        c for c in (proc.title or "item")[:30] if c.isalnum() or c in "-_ "
    ).strip()

    new_dir = old_path.parent.parent.parent / year / platform
    new_dir.mkdir(parents=True, exist_ok=True)
    new_path = new_dir / f"proc{proc.id}_{date_str}_{safe}.png"

    if old_path == new_path:
        skipped += 1
        continue

    try:
        old_path.rename(new_path)
        proc.screenshot_path = str(new_path)
        db.commit()
        print(f"  ✓ id={proc.id} {old_path.name} → {new_path.name}")
        renamed += 1
    except Exception as e:
        print(f"  ❌ id={proc.id} エラー: {e}")
        errors += 1

print(f"\n完了: リネーム{renamed}件 / スキップ{skipped}件 / エラー{errors}件")
