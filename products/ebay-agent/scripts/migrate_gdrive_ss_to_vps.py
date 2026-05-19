"""Google DriveのSSをVPS screenshotsディレクトリに移行してDBパスを更新する

Macで実行（GoogleドライブとVPS両方にアクセスできる環境）:
    cd products/ebay-agent
    python3 scripts/migrate_gdrive_ss_to_vps.py [--dry-run]

必要なもの:
    - VPS SSH接続 (root@46.250.252.99)
    - GoogleドライブがMacにマウントされていること
    - YAHOO_IMPORT_KEY が .env に設定されていること
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))

VPS_URL = os.getenv("EBAY_AGENT_URL", "https://ebay.trustlink-tk.com")
API_KEY = os.getenv("YAHOO_IMPORT_KEY", "")
VPS_HOST = "root@46.250.252.99"
VPS_SS_DIR = "/opt/apps/claude-workspace/products/ebay-agent/screenshots"


def api_call(path, method="GET", body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body else None
    headers = {"X-Import-Key": API_KEY}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        f"{VPS_URL}{path}", data=data, headers=headers, method=method
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def get_gdrive_records():
    """GoogleドライブパスのSSレコードをVPSから取得"""
    req = urllib.request.Request(
        f"{VPS_URL}/api/procurements/gdrive-screenshots",
        headers={"X-Import-Key": API_KEY},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main(dry_run=False):
    if not API_KEY:
        print("❌ YAHOO_IMPORT_KEY が設定されていません")
        sys.exit(1)

    print("GoogleドライブSSレコードを取得中...")
    records = get_gdrive_records()
    print(f"対象: {len(records)}件\n")

    transferred = skipped = failed = 0

    for rec in records:
        proc_id = rec["id"]
        src_path = rec["screenshot_path"]
        purchase_date = (
            rec.get("purchase_date", "")[:10].replace("-", "")
            if rec.get("purchase_date")
            else ""
        )
        platform = (rec.get("platform") or "other").replace("/", "_").replace(" ", "_")
        title = rec.get("title", "item")
        safe = "".join(c for c in title[:30] if c.isalnum() or c in "-_ ").strip()
        year = purchase_date[:4] if purchase_date else "2025"
        date_str = purchase_date or "unknown"
        new_filename = f"proc{proc_id}_{date_str}_{safe}.png"
        new_vps_path = f"{VPS_SS_DIR}/{year}/{platform}/{new_filename}"
        new_app_path = f"/app/screenshots/{year}/{platform}/{new_filename}"

        src = Path(src_path)
        if not src.exists():
            print(f"  [skip] id={proc_id} ファイルなし: {src_path[-60:]}")
            skipped += 1
            continue

        print(f"  id={proc_id} {src.name}")
        if dry_run:
            print(f"    → {new_vps_path[-70:]}")
            transferred += 1
            continue

        # rsyncでVPSへ転送
        vps_dir = f"{VPS_HOST}:{VPS_SS_DIR}/{year}/{platform}/"
        try:
            subprocess.run(
                ["ssh", VPS_HOST, f"mkdir -p {VPS_SS_DIR}/{year}/{platform}"],
                check=True,
                capture_output=True,
            )
            result = subprocess.run(
                ["rsync", "-a", str(src), f"{VPS_HOST}:{new_vps_path}"],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"    ❌ 転送失敗: {e}")
            failed += 1
            continue

        # DBパス更新
        try:
            api_call(
                f"/api/procurements/{proc_id}/update-screenshot-path",
                method="POST",
                body={"screenshot_path": new_app_path},
            )
            print(f"    ✓ → {new_app_path[-60:]}")
            transferred += 1
        except Exception as e:
            print(f"    ❌ DB更新失敗: {e}")
            failed += 1

    print(f"\n完了: 転送{transferred}件 / スキップ{skipped}件 / 失敗{failed}件")
    if dry_run:
        print("（dry-run: 実際の変更なし）")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
