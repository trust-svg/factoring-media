"""ローカルMacで手動ログインしてcookieを保存するヘルパー

使い方（products/ebay-agent/ から実行）:
    python scripts/login_and_save_cookies.py mercari
    python scripts/login_and_save_cookies.py yahoo
    python scripts/login_and_save_cookies.py yahoo_flea
    python scripts/login_and_save_cookies.py rakuma
    python scripts/login_and_save_cookies.py hardoff
    python scripts/login_and_save_cookies.py surugaya

ブラウザが開くので、指示されたページでログインしてEnterキーを押す。
cookieが .playwright/{site}_cookies.json に保存される。
その後 scripts/sync_cookies_to_vps.sh でVPSに同期する。
"""

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
COOKIE_DIR = ROOT / ".playwright"

SITES = {
    "mercari": {
        "file": "mercari_cookies.json",
        "url": "https://jp.mercari.com/login",
        "check_url": "https://jp.mercari.com/mypage/purchases",
        "label": "メルカリ",
    },
    "yahoo": {
        "file": "yahoo_cookies.json",
        "url": "https://login.yahoo.co.jp/config/login",
        "check_url": "https://auctions.yahoo.co.jp/my/won",
        "label": "Yahoo!オークション",
    },
    "yahoo_flea": {
        "file": "yahoo_flea_cookies.json",
        "url": "https://login.yahoo.co.jp/config/login",
        "check_url": "https://paypayfleamarket.yahoo.co.jp/mypage/purchased",
        "label": "Yahoo!フリマ",
    },
    "rakuma": {
        "file": "rakuma_cookies.json",
        "url": "https://fril.jp/users/login",
        "check_url": "https://fril.jp/mypage/purchases",
        "label": "ラクマ",
    },
    "hardoff": {
        "file": "hardoff_cookies.json",
        "url": "https://netmall.hardoff.co.jp/member/auth/login/",
        "check_url": "https://netmall.hardoff.co.jp/mypage/purchase_history/",
        "label": "ハードオフ",
    },
    "surugaya": {
        "file": "surugaya_cookies.json",
        "url": "https://www.suruga-ya.jp/pc/member_login.php",
        "check_url": "https://www.suruga-ya.jp/mypage/order_history.php",
        "label": "駿河屋",
    },
}


async def login_and_save(site_key: str):
    if site_key not in SITES:
        print(f"ERROR: unknown site '{site_key}'. Available: {', '.join(SITES.keys())}")
        sys.exit(1)

    from playwright.async_api import async_playwright

    site = SITES[site_key]
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    cookie_file = COOKIE_DIR / site["file"]

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-default-browser-check",
                "--disable-crash-reporter",
                "--no-crashpad",
            ],
        )
        context = await browser.new_context(
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            viewport={"width": 1280, "height": 800},
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = await context.new_page()
        print(f"[{site['label']}] ログインページを開きます: {site['url']}")
        await page.goto(site["url"], wait_until="domcontentloaded", timeout=30000)

        print("\n===== ログインしてください =====")
        print("ログインが完了したらEnterキーを押してください。\n")
        print("（まだcookieは保存しません）\n")

        input("[Enter] でログイン確認ページへ > ")

        print(f"\n次のページへ移動します: {site['check_url']}")
        print(
            "EEA/プライバシー通知が出た場合は「同意する」などをクリックして閉じてください。"
        )
        print("ページが正常に表示されたらEnterキーを押してcookieを保存します。\n")
        await page.goto(site["check_url"], wait_until="domcontentloaded", timeout=30000)

        input("[Enter] でcookie保存 > ")

        cookies = await context.cookies()
        cookie_file.write_text(json.dumps(cookies, ensure_ascii=False))
        print(f"✓ cookie保存: {cookie_file} ({len(cookies)}件)")

        await browser.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        print(f"\nAvailable sites: {', '.join(SITES.keys())}")
        sys.exit(1)
    asyncio.run(login_and_save(sys.argv[1]))
