"""API トークン期限・生存チェック.

実行: python -m tools.token_expiry [--json]

出力 (stdout): JSON
{
  "checked_at": "2026-05-10T05:00:00",
  "results": [
    {"name": "saimu-media Threads", "status": "warn", "days_left": 12, "expires_at": "2026-05-22"},
    {"name": "Meta Ads", "status": "ok", "note": "no expiry / long-lived"},
    {"name": "Google Ads", "status": "ok", "note": "refresh_token alive"},
    ...
  ]
}

監視対象:
- saimu-media Threads (Meta Graph debug_token / VPS .env を SSH 経由で読む)
- threads-auto Threads (Meta Graph debug_token / VPS .env を SSH 経由で読む)
- Meta Ads (Meta Graph debug_token / ローカル .env)
- Google Ads (OAuth refresh_token 生存確認 / ローカル .env)

トークン値は外部に出さない（残日数・期限日のみ stdout に出す）.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import dotenv_values

WARN_THRESHOLD_DAYS = 14

VPS_HOST = os.getenv("VPS_HOST", "root@46.250.252.99")


def _ssh_cat(remote_path: str) -> dict[str, str]:
    """VPS の .env を SSH 経由で読み、値の dict を返す."""
    try:
        result = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=15",
                VPS_HOST,
                f"cat {remote_path}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return {}
        env: dict[str, str] = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
        return env
    except Exception:
        return {}


def _check_threads(name: str, env: dict[str, str]) -> dict[str, Any]:
    token = env.get("THREADS_ACCESS_TOKEN")
    app_id = env.get("THREADS_APP_ID")
    app_secret = env.get("THREADS_APP_SECRET")
    if not all([token, app_id, app_secret]):
        return {"name": name, "status": "skip", "note": "credentials missing"}
    try:
        r = requests.get(
            "https://graph.facebook.com/v19.0/debug_token",
            params={
                "input_token": token,
                "access_token": f"{app_id}|{app_secret}",
            },
            timeout=15,
        )
        data = (r.json() or {}).get("data", {})
    except Exception as e:
        return {"name": name, "status": "error", "error": f"{type(e).__name__}: {e}"}

    if data.get("error"):
        return {"name": name, "status": "error", "error": str(data["error"])[:200]}
    if not data.get("is_valid", True):
        return {"name": name, "status": "error", "error": "token not valid"}

    expires_at = data.get("expires_at", 0)
    if expires_at in (0, None):
        return {"name": name, "status": "ok", "note": "no expiry / long-lived"}

    expires = datetime.fromtimestamp(expires_at, tz=timezone.utc)
    days_left = (expires - datetime.now(timezone.utc)).days
    status = "warn" if days_left <= WARN_THRESHOLD_DAYS else "ok"
    return {
        "name": name,
        "status": status,
        "days_left": days_left,
        "expires_at": expires.strftime("%Y-%m-%d"),
    }


def _check_meta_ads(env: dict[str, str]) -> dict[str, Any]:
    token = env.get("META_ACCESS_TOKEN")
    app_id = env.get("META_APP_ID") or env.get("FB_APP_ID")
    app_secret = env.get("META_APP_SECRET") or env.get("FB_APP_SECRET")
    if not token:
        return {
            "name": "Meta Ads",
            "status": "skip",
            "note": "META_ACCESS_TOKEN missing",
        }

    # APP_ID/SECRET があれば debug_token、無ければ /me で生存確認のみ
    if app_id and app_secret:
        try:
            r = requests.get(
                "https://graph.facebook.com/v19.0/debug_token",
                params={
                    "input_token": token,
                    "access_token": f"{app_id}|{app_secret}",
                },
                timeout=15,
            )
            data = (r.json() or {}).get("data", {})
        except Exception as e:
            return {
                "name": "Meta Ads",
                "status": "error",
                "error": f"{type(e).__name__}: {e}",
            }

        if data.get("error"):
            return {
                "name": "Meta Ads",
                "status": "error",
                "error": str(data["error"])[:200],
            }
        if not data.get("is_valid", True):
            return {"name": "Meta Ads", "status": "error", "error": "token not valid"}
        expires_at = data.get("expires_at", 0)
        if expires_at in (0, None):
            return {
                "name": "Meta Ads",
                "status": "ok",
                "note": "no expiry / long-lived",
            }
        expires = datetime.fromtimestamp(expires_at, tz=timezone.utc)
        days_left = (expires - datetime.now(timezone.utc)).days
        status = "warn" if days_left <= WARN_THRESHOLD_DAYS else "ok"
        return {
            "name": "Meta Ads",
            "status": status,
            "days_left": days_left,
            "expires_at": expires.strftime("%Y-%m-%d"),
        }

    # APP credentials なし: debug_token をトークン自身で叩く (self-debug)。
    # User token は input_token=access_token=自分自身 で expires_at を取得できる。
    try:
        r = requests.get(
            "https://graph.facebook.com/v19.0/debug_token",
            params={"input_token": token, "access_token": token},
            timeout=15,
        )
        data = (r.json() or {}).get("data", {})
        if not data.get("error") and data.get("is_valid", False):
            expires_at = data.get("expires_at", 0)
            if expires_at in (0, None):
                return {
                    "name": "Meta Ads",
                    "status": "ok",
                    "note": "no expiry / long-lived",
                }
            expires = datetime.fromtimestamp(expires_at, tz=timezone.utc)
            days_left = (expires - datetime.now(timezone.utc)).days
            status = "warn" if days_left <= WARN_THRESHOLD_DAYS else "ok"
            return {
                "name": "Meta Ads",
                "status": status,
                "days_left": days_left,
                "expires_at": expires.strftime("%Y-%m-%d"),
            }
    except Exception:
        pass  # self-debug 失敗 → /me フォールバックへ

    # フォールバック: /me で生存確認のみ
    try:
        r = requests.get(
            "https://graph.facebook.com/v19.0/me",
            params={"access_token": token},
            timeout=15,
        )
        if r.status_code == 200:
            return {
                "name": "Meta Ads",
                "status": "ok",
                "note": "alive (debug_token n/a)",
            }
        return {
            "name": "Meta Ads",
            "status": "error",
            "error": f"HTTP {r.status_code}: {r.text[:200]}",
        }
    except Exception as e:
        return {
            "name": "Meta Ads",
            "status": "error",
            "error": f"{type(e).__name__}: {e}",
        }


def _check_google_ads(env: dict[str, str]) -> dict[str, Any]:
    creds_path = env.get("GOOGLE_ADS_CREDENTIALS_PATH")
    if not creds_path:
        return {
            "name": "Google Ads",
            "status": "skip",
            "note": "GOOGLE_ADS_CREDENTIALS_PATH missing",
        }
    creds_path = os.path.expanduser(creds_path)
    if not os.path.exists(creds_path):
        return {
            "name": "Google Ads",
            "status": "skip",
            "note": f"creds file not found: {creds_path}",
        }

    try:
        if creds_path.endswith(".json"):
            with open(creds_path) as f:
                creds = json.load(f)
        else:
            try:
                import yaml  # type: ignore
            except ImportError:
                return {
                    "name": "Google Ads",
                    "status": "skip",
                    "note": "yaml module not installed",
                }
            with open(creds_path) as f:
                creds = yaml.safe_load(f) or {}
    except Exception as e:
        return {
            "name": "Google Ads",
            "status": "error",
            "error": f"creds load: {type(e).__name__}: {e}",
        }

    client_id = creds.get("client_id")
    client_secret = creds.get("client_secret")
    refresh_token = creds.get("refresh_token")
    if not all([client_id, client_secret, refresh_token]):
        return {
            "name": "Google Ads",
            "status": "skip",
            "note": "credentials incomplete",
        }

    try:
        r = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=15,
        )
    except Exception as e:
        return {
            "name": "Google Ads",
            "status": "error",
            "error": f"{type(e).__name__}: {e}",
        }

    if r.status_code == 200:
        return {"name": "Google Ads", "status": "ok", "note": "refresh_token alive"}
    return {
        "name": "Google Ads",
        "status": "error",
        "error": f"HTTP {r.status_code}: {r.text[:200]}",
    }


def main() -> int:
    workspace = Path.home() / "Claude-Workspace"
    results: list[dict[str, Any]] = []

    # Threads (saimu-media) — VPS から
    saimu_env = _ssh_cat("/opt/apps/saimu-media/.env")
    if not saimu_env:
        # フォールバック: sns-engine 配下の .env を確認
        saimu_env = _ssh_cat("/opt/apps/saimu-media/sns-engine/.env")
    results.append(_check_threads("saimu-media Threads", saimu_env))

    # Threads (threads-auto) — VPS から
    threads_env = _ssh_cat("/opt/apps/threads-auto/.env")
    results.append(_check_threads("threads-auto Threads", threads_env))

    # Meta Ads — ローカル
    meta_env = dotenv_values(workspace / "marketing" / "meta-ads-mcp" / ".env")
    if not meta_env.get("META_ACCESS_TOKEN"):
        # フォールバック: meta-ads/.env
        meta_env = dotenv_values(workspace / "marketing" / "meta-ads" / ".env")
    results.append(_check_meta_ads(meta_env))  # type: ignore[arg-type]

    # Google Ads — ローカル
    gads_env = dotenv_values(workspace / "marketing" / "google-ads-mcp" / ".env")
    results.append(_check_google_ads(gads_env))  # type: ignore[arg-type]

    output = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "results": results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

    has_warn_or_error = any(r.get("status") in ("warn", "error") for r in results)
    return 1 if has_warn_or_error else 0


if __name__ == "__main__":
    sys.exit(main())
