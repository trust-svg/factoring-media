"""SSなし・URLありの仕入れ記録に対してスクリーンショットを補完する

ローカルMacで実行。Playwrightでページを開いてSSを撮影し、VPSに送信する。

使い方（products/ebay-agent/ から実行）:
    python3 scripts/screenshot_patch.py

.env から読む:
    EBAY_AGENT_URL   — VPS URL（デフォルト: https://ebay.trustlink-tk.com）
    YAHOO_IMPORT_KEY — APIキー
"""

import asyncio
import base64
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


def api_get(path: str) -> list:
    req = urllib.request.Request(
        f"{VPS_URL}{path}",
        headers={"X-Import-Key": API_KEY},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read())


def api_post(path: str, body: dict) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{VPS_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json", "X-Import-Key": API_KEY},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read())


async def screenshot_url(page, url: str):
    try:
        await page.goto(url, wait_until="networkidle", timeout=20000)
        await page.wait_for_timeout(1500)
        return await page.screenshot(full_page=True)
    except Exception as e:
        print(f"    ⚠️  撮影失敗: {e}")
        return None


async def main() -> None:
    from playwright.async_api import async_playwright

    if not API_KEY:
        print("❌ YAHOO_IMPORT_KEY が .env に設定されていません")
        sys.exit(1)

    print("SSなし・URLありレコードを取得中...")
    targets = api_get("/api/procurements/missing-screenshots")
    if not targets:
        print("✓ 補完対象なし")
        return

    print(f"対象: {len(targets)}件\n")

    tmp_dir = Path(os.getenv("TMPDIR", "/tmp")) / "ss_patch"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    patched = skipped = failed = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        for item in targets:
            proc_id = item["id"]
            url = item["url"]
            title = item["title"][:40]
            print(f"[{proc_id}] {title}")
            print(f"    URL: {url}")

            ss_bytes = await screenshot_url(page, url)
            if ss_bytes is None:
                failed += 1
                continue

            b64_str = base64.b64encode(ss_bytes).decode("ascii")
            try:
                result = api_post(
                    f"/api/procurements/{proc_id}/screenshot-patch",
                    {"screenshot_b64": b64_str},
                )
                status = result.get("status", "?")
                if status == "patched":
                    print(f"    ✓ 保存: {result.get('path', '')}")
                    patched += 1
                else:
                    print(f"    ⏭ {result.get('reason', status)}")
                    skipped += 1
            except urllib.error.HTTPError as e:
                print(f"    ❌ APIエラー {e.code}: {e.read().decode()}")
                failed += 1
            except (urllib.error.URLError, OSError) as e:
                print(f"    ❌ 送信エラー: {e}")
                failed += 1

        await browser.close()

    print(f"\n完了: 補完{patched}件 / スキップ{skipped}件 / 失敗{failed}件")


if __name__ == "__main__":
    asyncio.run(main())
