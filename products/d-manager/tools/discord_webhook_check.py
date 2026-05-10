"""Discord Webhook 死活監視.

実行: python -m tools.discord_webhook_check [--json]

使用中の Discord Webhook URL を集めて GET し、404 (Unknown Webhook) や
401 (Invalid Token) などの異常を検知する.

URL 値は外部に出さず、ID 部分（最初の 19 桁）のみを表示する.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import requests
from dotenv import dotenv_values

# 監視対象の env file -> 取り出すキーの一覧.
# 同じ webhook が複数 env で使われていても、URL でユニーク化される.
ENV_TARGETS: list[tuple[str, list[str]]] = [
    (
        "~/Library/TrustLink/.env",
        ["DISCORD_MARKETING_WEBHOOK"],
    ),
    (
        "~/Library/TrustLink/google-ads.env",
        ["DISCORD_MARKETING_WEBHOOK"],
    ),
    (
        "~/Library/TrustLink/meta-ads-vps.env",
        ["DISCORD_MARKETING_WEBHOOK"],
    ),
    (
        "~/Library/TrustLink/google-ads-vps.env",
        ["DISCORD_MARKETING_WEBHOOK"],
    ),
    (
        "~/Claude-Workspace/marketing/meta-ads/.env",
        ["DISCORD_MARKETING_WEBHOOK"],
    ),
    (
        "~/Claude-Workspace/marketing/google-ads/.env",
        ["DISCORD_MARKETING_WEBHOOK"],
    ),
    (
        "~/Claude-Workspace/products/ebay-agent/.env",
        ["DISCORD_WEBHOOK_REFRESH"],
    ),
    (
        "~/Claude-Workspace/products/ai-daily-digest/.env",
        ["DISCORD_WEBHOOK_URL"],
    ),
]

# notify.py や他コード内ハードコード Webhook を抽出するソースファイル (ローカル).
HARDCODED_SOURCES: list[str] = [
    "~/Claude-Workspace/marketing/google-ads/rotation/notify.py",
    "~/Claude-Workspace/products/ai-uranai/scripts/weekly_analysis.py",
]

# VPS 上のスクリプトに埋め込まれた Webhook を SSH 越しに読み取る.
# (ssh_host, remote_path) のタプル.
SSH_HARDCODED_SOURCES: list[tuple[str, str]] = [
    ("root@46.250.252.99", "/opt/backups/backup.sh"),
]

WEBHOOK_RE = re.compile(
    r"https://discord\.com/api/webhooks/(\d{17,20})/[A-Za-z0-9_\-]+"
)


def _short(url: str) -> str:
    """URL から ID 部分だけ返す。値の漏洩を避ける."""
    m = WEBHOOK_RE.search(url)
    return f"webhook:{m.group(1)}" if m else "webhook:<unknown>"


def _collect_webhooks() -> dict[str, list[str]]:
    """{url: [使用箇所...]} の辞書を返す."""
    found: dict[str, list[str]] = {}

    for env_path_str, keys in ENV_TARGETS:
        p = Path(env_path_str).expanduser()
        if not p.exists():
            continue
        # 親ディレクトリ込みで識別 (e.g. "TrustLink/.env", "meta-ads/.env")
        location = f"{p.parent.name}/{p.name}"
        env = dotenv_values(p)
        for k in keys:
            url = env.get(k, "").strip()
            if url and WEBHOOK_RE.search(url):
                found.setdefault(url, []).append(f"{location}:{k}")

    for src_path_str in HARDCODED_SOURCES:
        p = Path(src_path_str).expanduser()
        if not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        location = f"{p.parent.name}/{p.name}"
        for m in WEBHOOK_RE.finditer(text):
            url = m.group(0)
            found.setdefault(url, []).append(location)

    for ssh_host, remote_path in SSH_HARDCODED_SOURCES:
        try:
            result = subprocess.run(
                [
                    "ssh",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "ConnectTimeout=10",
                    ssh_host,
                    "cat",
                    remote_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception:
            continue
        if result.returncode != 0:
            continue
        text = result.stdout
        location = f"{ssh_host}:{Path(remote_path).name}"
        for m in WEBHOOK_RE.finditer(text):
            url = m.group(0)
            found.setdefault(url, []).append(location)

    return found


def _check(url: str) -> dict[str, Any]:
    """単一 webhook を GET して状態を返す."""
    try:
        r = requests.get(url, timeout=10)
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}

    if r.status_code == 200:
        try:
            data = r.json()
        except Exception:
            data = {}
        return {
            "status": "ok",
            "channel_id": data.get("channel_id"),
            "name": data.get("name"),
        }
    if r.status_code == 404:
        return {"status": "dead", "error": "Unknown Webhook (404)"}
    if r.status_code == 401:
        return {"status": "dead", "error": "Invalid Token (401)"}
    return {"status": "error", "error": f"HTTP {r.status_code}"}


def main() -> int:
    webhooks = _collect_webhooks()
    results: list[dict[str, Any]] = []

    for url, used_in in sorted(webhooks.items()):
        check = _check(url)
        results.append(
            {
                "id": _short(url),
                "used_in": sorted(set(used_in)),
                **check,
            }
        )

    output = {"results": results}
    print(json.dumps(output, ensure_ascii=False, indent=2))

    has_problem = any(r.get("status") in ("dead", "error") for r in results)
    return 1 if has_problem else 0


if __name__ == "__main__":
    sys.exit(main())
