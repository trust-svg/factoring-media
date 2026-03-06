"""
eBay OAuth2.0 初回認証セットアップスクリプト
初回のみ実行してください。tokens/ebay_token.json が生成されます。

実行方法:
    python setup_ebay_oauth.py
"""
import json
import time
import urllib.parse
import webbrowser
from base64 import b64encode
from pathlib import Path

import requests

import sys
sys.path.insert(0, str(Path(__file__).parent))
from config import (
    EBAY_CLIENT_ID,
    EBAY_CLIENT_SECRET,
    EBAY_REDIRECT_URI,
    EBAY_AUTH_BASE,
    EBAY_OAUTH_SCOPES,
    EBAY_TOKEN_FILE,
)


def main():
    print("=" * 60)
    print("eBay OAuth2.0 初期設定 (Listing SEO Optimizer)")
    print("=" * 60)

    if not EBAY_CLIENT_ID or not EBAY_CLIENT_SECRET:
        print("\nエラー: .env ファイルに EBAY_CLIENT_ID と EBAY_CLIENT_SECRET を設定してください")
        print("  .env.example を参考にしてください")
        return

    # Step 1: 認証URLを生成してブラウザで開く
    auth_params = {
        "client_id": EBAY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": EBAY_REDIRECT_URI,
        "scope": EBAY_OAUTH_SCOPES,
        "state": "ebay_optimizer_auth",
    }
    auth_url = f"{EBAY_AUTH_BASE}/oauth2/authorize?" + urllib.parse.urlencode(auth_params)

    print("\n[Step 1] 以下のURLをブラウザで開いてeBayにログインし、アクセスを許可してください:")
    print(f"\n  {auth_url}\n")

    open_browser = input("ブラウザを自動で開きますか？ (y/n): ").strip().lower()
    if open_browser == "y":
        webbrowser.open(auth_url)

    print("\n[Step 2] リダイレクト後のURLから 'code=' の値をコピーして貼り付けてください")
    print("  例: https://your-redirect-uri?code=XXXXXXXX&state=ebay_optimizer_auth")
    auth_code = input("\n  code= の値を入力: ").strip()

    if not auth_code:
        print("エラー: 認証コードが入力されませんでした")
        return

    # Step 3: authorization_code → access_token + refresh_token に交換
    credentials = b64encode(f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}".encode()).decode()
    try:
        resp = requests.post(
            f"{EBAY_AUTH_BASE}/identity/v1/oauth2/token",
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": EBAY_REDIRECT_URI,
            },
            timeout=15,
        )
        resp.raise_for_status()
    except requests.HTTPError as e:
        print(f"\nトークン取得失敗: {e}")
        print(f"  レスポンス: {resp.text}")
        return

    data = resp.json()
    token_data = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", ""),
        "expires_at": time.time() + data.get("expires_in", 7200),
        "refresh_token_expires_at": time.time() + data.get("refresh_token_expires_in", 47304000),
    }

    EBAY_TOKEN_FILE.parent.mkdir(exist_ok=True)
    with open(EBAY_TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)

    print(f"\n認証成功！トークンを保存しました: {EBAY_TOKEN_FILE}")
    print("  アクセストークン有効期限: 約2時間（自動更新されます）")
    print("  リフレッシュトークン有効期限: 約18ヶ月")
    print("\n次は python main.py を実行してサーバーを起動してください。")


if __name__ == "__main__":
    main()
