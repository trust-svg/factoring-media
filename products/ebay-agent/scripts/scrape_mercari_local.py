"""ローカルMacでメルカリ購入履歴をスクレイプしてVPSに取込む

ローカルMacで実行してメルカリにログインし、結果をVPS APIにPOSTする。

使い方（products/ebay-agent/ から実行）:
    python3 scripts/scrape_mercari_local.py

.env から読む:
    EBAY_AGENT_URL   — VPS URL（デフォルト: https://ebay.trustlink-tk.com）
    YAHOO_IMPORT_KEY — APIキー（VPS .env と同じ値）
"""

import asyncio
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# .env 読み込み（python-dotenv 不要）
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
    from scrapers.mercari import scrape_mercari_purchases

    if not API_KEY:
        print("❌ YAHOO_IMPORT_KEY が .env に設定されていません")
        sys.exit(1)

    print("メルカリ購入履歴をスクレイプ中（ローカルMac実行）...")
    print("  ※ セッション切れの場合はブラウザが開きます。ログインしてください。")
    try:
        results = await scrape_mercari_purchases(
            on_progress=on_progress, headless=False
        )
    except RuntimeError as e:
        if "LOGIN_REQUIRED" in str(e):
            print(
                "❌ メルカリセッション切れ。ブラウザが開かない場合は headless=False を確認してください"
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
        f"{VPS_URL}/api/procurements/mercari-local-import",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Import-Key": API_KEY,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_err = e.read().decode("utf-8", errors="replace")
        print(f"❌ HTTPエラー {e.code}: {body_err}")
        sys.exit(1)

    print(
        f"✓ 取込完了: 新規{data['imported']}件 / スキップ{data['skipped']}件（重複）"
        f" / 合計{data['total']}件"
    )


if __name__ == "__main__":
    asyncio.run(main())
