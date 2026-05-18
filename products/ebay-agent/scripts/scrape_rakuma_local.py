"""ローカルMacでラクマ購入履歴をスクレイプしてVPSに取込む"""

import asyncio
import json
import os
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


def on_progress(msg: str, current: int, total: int) -> None:
    print(f"  {msg}")


async def main() -> None:
    from scrapers.rakuma_purchases import scrape_rakuma_purchases

    if not API_KEY:
        print("❌ YAHOO_IMPORT_KEY が .env に設定されていません")
        sys.exit(1)

    print("ラクマ購入履歴をスクレイプ中（ローカルMac実行）...")
    try:
        results = await scrape_rakuma_purchases(on_progress=on_progress, headless=False)
    except RuntimeError as e:
        if "LOGIN_REQUIRED" in str(e):
            print(
                "❌ ラクマセッション切れ。ブラウザが開かない場合は再ログインしてください"
            )
            sys.exit(1)
        raise

    if not results:
        print("⚠️  取得件数0件")
        return

    print(f"✓ スクレイプ完了: {len(results)}件")
    print(f"VPS ({VPS_URL}) に取込中...")

    body = json.dumps(results, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{VPS_URL}/api/procurements/rakuma-local-import",
        data=body,
        headers={"Content-Type": "application/json", "X-Import-Key": API_KEY},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"❌ HTTPエラー {e.code}: {e.read().decode('utf-8', errors='replace')}")
        sys.exit(1)

    print(
        f"✓ 取込完了: 新規{data['imported']}件 / スキップ{data['skipped']}件（重複）"
        f" / 合計{data['total']}件"
    )


if __name__ == "__main__":
    asyncio.run(main())
