"""eBay OAuth2 トークン管理"""
from __future__ import annotations

import json
import logging
import time
from base64 import b64encode

import requests

from config import (
    EBAY_API_BASE,
    EBAY_AUTH_BASE,
    EBAY_CLIENT_ID,
    EBAY_CLIENT_SECRET,
    EBAY_OAUTH_SCOPES,
    EBAY_TOKEN_FILE,
)

logger = logging.getLogger(__name__)


def _load_token() -> dict:
    if EBAY_TOKEN_FILE.exists():
        with open(EBAY_TOKEN_FILE) as f:
            return json.load(f)
    return {}


def _save_token(token_data: dict):
    EBAY_TOKEN_FILE.parent.mkdir(exist_ok=True)
    with open(EBAY_TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)


def _is_token_expired(token_data: dict) -> bool:
    expires_at = token_data.get("expires_at", 0)
    return time.time() >= expires_at - 60


def _refresh_access_token(token_data: dict) -> str:
    """refresh_token を使ってアクセストークンを更新"""
    refresh_token = token_data.get("refresh_token", "")
    if not refresh_token:
        raise RuntimeError(
            "refresh_token が見つかりません。setup_ebay_oauth.py を実行してください。"
        )

    credentials = b64encode(
        f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}".encode()
    ).decode()
    resp = requests.post(
        f"{EBAY_AUTH_BASE}/identity/v1/oauth2/token",
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": EBAY_OAUTH_SCOPES,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    token_data["access_token"] = data["access_token"]
    token_data["expires_at"] = time.time() + data.get("expires_in", 7200)
    _save_token(token_data)
    logger.info("eBayアクセストークンを更新しました")
    return data["access_token"]


def get_access_token() -> str:
    """有効なアクセストークンを返す（必要なら自動更新）"""
    token_data = _load_token()
    if not token_data:
        raise RuntimeError(
            "eBayトークンが見つかりません。\n"
            "python setup_ebay_oauth.py を実行してeBay認証を完了してください。"
        )
    if _is_token_expired(token_data):
        return _refresh_access_token(token_data)
    return token_data["access_token"]


def get_auth_headers() -> dict[str, str]:
    """認証ヘッダーを返す"""
    token = get_access_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
