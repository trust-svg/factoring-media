"""VPS DB バックアップ整合性チェック (Tier 3-H).

実行: python -m tools.backup_integrity_check [--json]

対象: VPS `/opt/backups/db/` 配下のバックアップファイル.
SSH 越しに stat を取得し、期待ファイルが 24h 以内に更新されているか・
極端にサイズが小さくなっていないかを判定する.

二段階の期待リスト:
- REQUIRED: 既に backup.sh が取っているもの → 古い/欠落は WARN/CRIT
- PENDING_SETUP: 本来必要だが backup.sh 未対応のもの → INFO のみ（毎朝可視化）
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from typing import Any

VPS_HOST = "root@46.250.252.99"
BACKUP_DB_DIR = "/opt/backups/db"

# 既に backup.sh が取得しているファイル. 古い/欠落は警告対象.
REQUIRED_BACKUPS: list[dict[str, Any]] = [
    {
        "name": "ebay-agent.db",
        "label": "ebay-agent SQLite",
        "max_age_hours": 26,
        "min_size_bytes": 100_000,
    },
    {
        "name": "zinq.db",
        "label": "ZINQ/messecoach SQLite",
        "max_age_hours": 26,
        "min_size_bytes": 8_192,
    },
]

# 本来バックアップしたいが backup.sh 未対応のもの. 毎朝の可視化のみ.
PENDING_SETUP: list[dict[str, Any]] = [
    {
        "name": "ai-uranai.dump",
        "label": "ai-uranai PostgreSQL",
    },
    {
        "name": "threads-auto.db",
        "label": "threads-auto SQLite",
    },
    {
        "name": "saimu-media.db",
        "label": "saimu-media sns-engine SQLite",
    },
]


def _ssh_stat() -> tuple[dict[str, tuple[int, float]] | None, str | None]:
    """VPS に SSH して /opt/backups/db/ 配下のファイル情報を取得.

    返り値: ({filename: (size_bytes, mtime_epoch)}, error_message)
    """
    try:
        result = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                VPS_HOST,
                f"find {BACKUP_DB_DIR} -maxdepth 1 -type f -printf '%f\\t%s\\t%T@\\n'",
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
        return None, f"ssh failed: {err}"

    files: dict[str, tuple[int, float]] = {}
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        name, size_str, mtime_str = parts
        try:
            files[name] = (int(size_str), float(mtime_str))
        except ValueError:
            continue
    return files, None


def _evaluate_required(
    spec: dict[str, Any],
    files: dict[str, tuple[int, float]],
    now: float,
) -> dict[str, Any]:
    name = spec["name"]
    label = spec["label"]
    if name not in files:
        return {
            "name": name,
            "label": label,
            "status": "missing",
            "error": "ファイルが存在しない",
        }
    size, mtime = files[name]
    age_hours = (now - mtime) / 3600.0
    age_str = f"{age_hours:.1f}h"

    if size < spec["min_size_bytes"]:
        return {
            "name": name,
            "label": label,
            "status": "undersized",
            "size_bytes": size,
            "age_hours": round(age_hours, 1),
            "error": f"size={size} < min={spec['min_size_bytes']}",
        }
    if age_hours > spec["max_age_hours"]:
        return {
            "name": name,
            "label": label,
            "status": "stale",
            "size_bytes": size,
            "age_hours": round(age_hours, 1),
            "error": f"age={age_str} > max={spec['max_age_hours']}h",
        }
    return {
        "name": name,
        "label": label,
        "status": "ok",
        "size_bytes": size,
        "age_hours": round(age_hours, 1),
    }


def _evaluate_pending(
    spec: dict[str, Any],
    files: dict[str, tuple[int, float]],
    now: float,
) -> dict[str, Any]:
    name = spec["name"]
    label = spec["label"]
    if name in files:
        size, mtime = files[name]
        age_hours = (now - mtime) / 3600.0
        return {
            "name": name,
            "label": label,
            "status": "ok",  # 整備された
            "size_bytes": size,
            "age_hours": round(age_hours, 1),
        }
    return {
        "name": name,
        "label": label,
        "status": "no_backup_setup",
        "error": "backup.sh 未対応",
    }


def main() -> int:
    files, ssh_error = _ssh_stat()
    if ssh_error is not None:
        output = {"ssh_error": ssh_error, "required": [], "pending_setup": []}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 1

    assert files is not None
    now = time.time()

    required_results = [_evaluate_required(s, files, now) for s in REQUIRED_BACKUPS]
    pending_results = [_evaluate_pending(s, files, now) for s in PENDING_SETUP]

    output = {
        "ssh_error": None,
        "required": required_results,
        "pending_setup": pending_results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

    has_problem = any(
        r.get("status") in ("missing", "stale", "undersized") for r in required_results
    )
    return 1 if has_problem else 0


if __name__ == "__main__":
    sys.exit(main())
