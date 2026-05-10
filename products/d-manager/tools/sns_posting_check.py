"""SNS 0 投稿アラート (Tier 3-I).

実行: python -m tools.sns_posting_check [--json]

対象: saimu-media Threads (`/var/log/saimu-threads.log`).
過去 24h 以内の「✅ Threads投稿完了」行数をカウントし、0 件なら異常.

threads-auto / faxcel-x-auto は本実装ではスコープ外（別タスク）.

VPS ホスト TZ は Asia/Tokyo (memory 参照) を前提とする.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

VPS_HOST = "root@46.250.252.99"

JST = timezone(timedelta(hours=9))

# 監視対象 SNS 一覧.
TARGETS: list[dict[str, Any]] = [
    {
        "name": "saimu-media-threads",
        "label": "saimu-media Threads (saimutimes)",
        "log_path": "/var/log/saimu-threads.log",
        "success_marker": "Threads投稿完了",
        "min_posts_24h": 1,
    },
]


def _count_recent_posts(target: dict[str, Any]) -> tuple[int | None, str | None]:
    """SSH 越しに過去 24h の成功投稿数をカウント.

    返り値: (count, error_message). count==None なら error.
    """
    cutoff = (datetime.now(JST) - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    marker = target["success_marker"]
    log_path = target["log_path"]

    awk_script = (
        f"awk -v cutoff='{cutoff}' "
        f"'$0 >= cutoff && /{marker}/ {{c++}} END {{print c+0}}' "
        f"{log_path}"
    )
    try:
        result = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                VPS_HOST,
                awk_script,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return None, "ssh timeout (>30s)"
    except Exception as e:
        return None, f"ssh exec error: {type(e).__name__}: {e}"

    if result.returncode != 0:
        err = result.stderr.strip() or f"exit={result.returncode}"
        return None, f"ssh/awk failed: {err}"

    out = result.stdout.strip()
    if not out:
        return None, "empty stdout (log file missing?)"

    try:
        return int(out), None
    except ValueError:
        return None, f"non-integer output: {out!r}"


def main() -> int:
    results: list[dict[str, Any]] = []

    for target in TARGETS:
        count, err = _count_recent_posts(target)
        if err is not None:
            results.append(
                {
                    "name": target["name"],
                    "label": target["label"],
                    "status": "error",
                    "error": err,
                }
            )
            continue
        assert count is not None
        if count >= target["min_posts_24h"]:
            results.append(
                {
                    "name": target["name"],
                    "label": target["label"],
                    "status": "ok",
                    "posts_24h": count,
                }
            )
        else:
            results.append(
                {
                    "name": target["name"],
                    "label": target["label"],
                    "status": "zero_posts",
                    "posts_24h": count,
                    "error": (
                        f"過去24hの投稿数 {count} < min={target['min_posts_24h']}"
                    ),
                }
            )

    output = {"results": results}
    print(json.dumps(output, ensure_ascii=False, indent=2))

    has_problem = any(r.get("status") in ("zero_posts", "error") for r in results)
    return 1 if has_problem else 0


if __name__ == "__main__":
    sys.exit(main())
