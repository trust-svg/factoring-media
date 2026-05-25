"""Scheduled tasks — morning briefing, evening review, task board, KPI reports."""

import logging
import asyncio
import functools
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import EVENT_JOB_ERROR
import httpx

import config
from ai_engine import process_message
from tools.dream import get_dream_briefing, get_pyramid_summary, list_dreams
from tools.divination import get_daily_summary, get_monthly_summary

logger = logging.getLogger(__name__)
_scheduler: Optional[AsyncIOScheduler] = None
_scheduler_started = False  # True once start() has been called
_send_fn = None  # send_to_channel(channel_name, text, view=None)
_task_view_fn = None  # function to create TaskBoardView(tasks)


async def _send_telegram_alert(text: str) -> None:
    """夜間QA異常時にTelegramへ通知。トークン未設定時はサイレントスキップ。"""
    token = os.getenv("TELEGRAM_BOT_TOKEN_DMANAGER")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "323107833")
    if not token:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            )
    except Exception as e:
        logger.warning(f"Telegram alert failed: {e}")


JST = timezone(timedelta(hours=9))
ACTIVE_TASKS_PATH = config.COMPANY_DIR / "secretary" / "todos" / "active.md"
NIGHTLY_QA_PATH = config.COMPANY_DIR / "secretary" / "logs" / "nightly_qa.md"

# Department -> channel mapping for task routing
DEPT_CHANNELS = {
    "Steve": "ceo-steve-general",
    "Jack": "運営-jack-operations",
    "Larry": "開発-larry-product",
    "Mark": "マーケティング-mark-marketing",
    "Warren": "経理-warren-finance",
    "Elon": "調査-elon-research",
    "Reid": "戦略-reid-strategy",
}

# Tier 3-A: 夜間サイト疎通チェック対象
NIGHTLY_QA_SITES = [
    ("ebay-agent", "https://ebay.trustlink-tk.com"),
    ("FACCEL", "https://faccel.jp"),
    ("債務整理タイムズ", "https://saimu-times.com"),
    ("Sion", "https://sion.trustlink-tk.com/health"),
    ("Threads-auto", "https://threads-sho.trustlink-tk.com"),
    ("video-analyzer", "https://video.trustlink-tk.com/docs"),
]

# Tier 3-B: 夜間コミットレビュー対象（24h以内のコミットがあれば diff レビュー）
# 独立 git repo / monorepo サブパス両対応（has_own_git で切り替え）
NIGHTLY_COMMIT_TARGETS = [
    # monorepo 配下（Claude-Workspace の git で管理）
    Path.home() / "Claude-Workspace" / "products" / "ebay-agent",
    Path.home() / "Claude-Workspace" / "products" / "d-manager",
    Path.home() / "Claude-Workspace" / "products" / "threads-auto",
    Path.home() / "Claude-Workspace" / "products" / "deal-watcher",
    Path.home() / "Claude-Workspace" / "products" / "b-manager",
    Path.home() / "Claude-Workspace" / "products" / "sukoyaka-assets",
    # 独立 git repo
    Path.home() / "Claude-Workspace" / "products" / "saimu-media",
    Path.home() / "Claude-Workspace" / "products" / "messecoach",
    Path.home() / "Claude-Workspace" / "products" / "factoring-media",
    Path.home() / "Claude-Workspace" / "products" / "ai-uranai",
    Path.home() / "Claude-Workspace" / "products" / "video-analyzer",
    Path.home() / "Claude-Workspace" / "products" / "ebay-inventory-tool",
    Path.home() / "Claude-Workspace" / "products" / "ai-daily-digest",
]
WORKSPACE_ROOT = Path.home() / "Claude-Workspace"


def _pick_daily_teaching() -> str:
    """Pick a daily teaching based on the date."""
    import random

    teachings = [
        "【7つの習慣】主体的であれ — 今日の出来事に対する反応は自分で選べる。",
        "【7つの習慣】目的を持って始める — 今日をどんな自分で終えたいか。",
        "【7つの習慣】重要事項を優先する — 緊急じゃないが重要なことに30分使おう。",
        "【ザ・パワー】良い感情こそが人生を動かすパワー。今何に愛を感じる？",
        "【ザ・パワー】感謝は最も強力なパワー。今あるものに心から感謝しよう。",
        "【鏡の法則】現実は自分の心を映す鏡。イラッとしたら自分の何が映っている？",
        "【夢ゾウ2】今日いつもと違う小さなチャレンジを1つやってみよう。",
    ]
    rng = random.Random(date.today().toordinal())
    return rng.choice(teachings)


def _parse_active_tasks() -> list:
    """Parse active.md and return list of task dicts (states: UN/IN/BL).

    DN（完了）は task board に出さないので parser でも拾わない。
    フォーマット:
      - [UN] 名 | 担当: X | 期限: Y | 追加: Z [| スキップ: N]
      - [IN] 名 | 担当: X | 期限: Y | 追加: Z
      - [BL] 名 | 担当: X | 期限: Y | 追加: Z | ブロック理由: …
    """
    if not ACTIVE_TASKS_PATH.exists():
        return []

    content = ACTIVE_TASKS_PATH.read_text(encoding="utf-8")
    tasks = []
    pattern = re.compile(
        r"^- \[(UN|IN|BL)\] (.+?) \| 担当: (\S+) \| 期限: (\S+) \| 追加: (\d{4}-\d{2}-\d{2})(.*?)$",
        re.MULTILINE,
    )
    for m in pattern.finditer(content):
        state = m.group(1)
        added = m.group(5)
        extra = m.group(6) or ""
        skip_match = re.search(r"スキップ:\s*(\d+)", extra)
        block_match = re.search(r"ブロック理由:\s*(.+?)(?:\s*\||$)", extra)
        try:
            days = (date.today() - date.fromisoformat(added)).days
        except ValueError:
            days = 0
        tasks.append(
            {
                "state": state,
                "name": m.group(2),
                "owner": m.group(3),
                "deadline": m.group(4),
                "added": added,
                "skip_count": int(skip_match.group(1)) if skip_match else 0,
                "block_reason": block_match.group(1).strip() if block_match else None,
                "age_days": days,
            }
        )
    return tasks


def _build_task_board() -> str:
    """Build a formatted task board message for Discord (state-aware: UN/IN/BL)."""
    tasks = _parse_active_tasks()
    today = date.today().isoformat()

    if not tasks:
        return f"📋 **タスクボード — {today}**\n\nタスクなし！素晴らしい！🎉"

    lines = [f"📋 **タスクボード — {today}**\n"]

    # 状態別に分類
    in_progress = [t for t in tasks if t["state"] == "IN"]
    blocked = [t for t in tasks if t["state"] == "BL"]
    un_tasks = [t for t in tasks if t["state"] == "UN"]

    # 着手中（IN）— 進捗確認の促し
    if in_progress:
        lines.append("🔵 **着手中（進捗確認）**")
        for t in in_progress:
            lines.append(f"  ▶ {t['name']} → {t['owner']}（{t['age_days']}日経過）")
        lines.append("")

    # ブロック中（BL）— 何待ちか可視化
    if blocked:
        lines.append("🟣 **ブロック中（解除待ち）**")
        for t in blocked:
            reason = t["block_reason"] or "理由未記入"
            lines.append(f"  ⏸ {t['name']} → {t['owner']}（{reason}）")
        lines.append("")

    # 未着手（UN）の中でさらに細分化
    urgent = [t for t in un_tasks if t["deadline"] != "なし" and t["deadline"] <= today]
    overdue = [t for t in un_tasks if t["age_days"] >= 7 and t not in urgent]
    warning = [t for t in un_tasks if 3 <= t["age_days"] < 7 and t not in urgent]
    normal = [t for t in un_tasks if t["age_days"] < 3 and t not in urgent]
    stale = [t for t in un_tasks if t["skip_count"] >= 3]

    if urgent:
        lines.append("🚨 **期限切れ・緊急（未着手）**")
        for t in urgent:
            lines.append(
                f"  ⚡ **{t['name']}** → {t['owner']}（期限: {t['deadline']}）"
            )
        lines.append("")

    if stale:
        lines.append("⚠️ **3回スキップ — やる？捨てる？**")
        for t in stale:
            lines.append(f"  🗑️ **{t['name']}** → {t['owner']}（{t['age_days']}日経過）")
        lines.append("")

    if overdue:
        lines.append("🟠 **7日以上放置（未着手）**")
        for t in overdue:
            lines.append(f"  📌 {t['name']} → {t['owner']}（{t['age_days']}日）")
        lines.append("")

    if warning:
        lines.append("🟡 **3日以上（未着手）**")
        for t in warning:
            lines.append(f"  📌 {t['name']} → {t['owner']}（{t['age_days']}日）")
        lines.append("")

    if normal:
        lines.append("🟢 **新規・通常（未着手）**")
        for t in normal:
            lines.append(f"  ✏️ {t['name']} → {t['owner']}")
        lines.append("")

    lines.append(
        f"合計: **{len(tasks)}件** "
        f"(🔵IN: {len(in_progress)} / 🟣BL: {len(blocked)} / ⚪UN: {len(un_tasks)}) "
        f"| 放置警告: {len(overdue)}件 | 要判断: {len(stale)}件"
    )
    return "\n".join(lines)


def _increment_skip_counts():
    """Increment skip count for UN tasks only (called at evening review).

    IN（着手中）/ BL（ブロック中）は意図的に放置されているのでカウントしない。
    既存行に「| スキップ: N」が無ければ「| スキップ: 1」を末尾に追加する。
    """
    if not ACTIVE_TASKS_PATH.exists():
        return

    content = ACTIVE_TASKS_PATH.read_text(encoding="utf-8")
    new_lines = []
    incremented = 0
    for line in content.split("\n"):
        if not line.startswith("- [UN]"):
            new_lines.append(line)
            continue

        m = re.search(r"\|\s*スキップ:\s*(\d+)", line)
        if m:
            new_count = int(m.group(1)) + 1
            updated_line = re.sub(
                r"\|\s*スキップ:\s*\d+", f"| スキップ: {new_count}", line
            )
        else:
            updated_line = f"{line.rstrip()} | スキップ: 1"
        new_lines.append(updated_line)
        incremented += 1

    updated = "\n".join(new_lines)

    # Update the 'updated' date in frontmatter
    updated = re.sub(
        r'updated: "\d{4}-\d{2}-\d{2}"',
        f'updated: "{date.today().isoformat()}"',
        updated,
    )
    ACTIVE_TASKS_PATH.write_text(updated, encoding="utf-8")
    logger.info(f"Skip counts incremented for {incremented} UN tasks")


def _api_get(url: str, timeout: int = 10):
    """Simple HTTP GET → JSON. Returns None on failure."""
    headers = {"User-Agent": "D-Manager/1.0"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as e:
        logger.warning(f"API fetch failed ({url}): {e}")
        return None


def _collect_kpi() -> dict:
    """Collect KPI data from external services for department reports."""
    kpi = {}

    # eBay KPI → Jack（運営）
    if config.EBAY_AGENT_URL:
        base = config.EBAY_AGENT_URL.rstrip("/")
        sales = _api_get(f"{base}/api/sales/summary?days=7")
        listings = _api_get(f"{base}/api/listings")
        parts = []
        if sales:
            parts.append(f"売上データ(7日): {json.dumps(sales, ensure_ascii=False)}")
        if listings and isinstance(listings, list):
            active = len(listings)
            oos = sum(1 for l in listings if l.get("quantity", 0) == 0)
            parts.append(f"出品数: {active}件, 在庫切れ: {oos}件")
        if parts:
            kpi["operations"] = "\n".join(parts)

    # Threads KPI → Mark（マーケティング）
    if config.THREADS_AUTO_URL:
        base = config.THREADS_AUTO_URL.rstrip("/")
        status = _api_get(f"{base}/api/status")
        if status:
            kpi["marketing"] = f"Threads状況: {json.dumps(status, ensure_ascii=False)}"

    return kpi


# --- Tier 3: 夜間QA（サイト疎通 + コミットレビュー） ---


async def nightly_site_check():
    """Tier 3-A: 深夜2:00 — 主要プロダクトサイト疎通確認。失敗のみJackに通知。"""
    logger.info("Running nightly_site_check...")

    today_iso = date.today().isoformat()
    results: list[str] = []
    failures: list[tuple[str, str, object]] = []

    # 判定: 200/401/403 はサーバー応答あり = 稼働 OK 扱い
    # （ebay-agent等は認証必須なので 401 が正常応答）
    OK_CODES = {200, 301, 302, 401, 403}

    for name, url in NIGHTLY_QA_SITES:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "D-Manager-NightlyQA/1.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                code = resp.status
                ok = code in OK_CODES
        except urllib.error.HTTPError as e:
            # HTTPError でも認証系（401/403）はサーバー稼働とみなす
            code = e.code
            ok = code in OK_CODES
        except Exception as e:
            code = f"ERR({type(e).__name__})"
            ok = False

        if ok:
            results.append(f"- ✅ {name}: HTTP {code}")
        else:
            results.append(f"- 🚨 {name}: {code} ({url})")
            failures.append((name, url, code))

    NIGHTLY_QA_PATH.parent.mkdir(parents=True, exist_ok=True)
    summary = (
        f"# 夜間QA サマリ ({today_iso})\n\n"
        f"## サイト疎通 (深夜2:00)\n" + "\n".join(results) + "\n"
    )
    NIGHTLY_QA_PATH.write_text(summary, encoding="utf-8")

    if failures and _send_fn:
        lines = [f"🚨 **夜間サイト疎通チェック失敗 ({len(failures)}件)**\n"]
        for name, url, code in failures:
            lines.append(f"- **{name}**: {code}\n  → {url}")
        msg = "\n".join(lines)
        await _send_fn("運営-jack-operations", msg)
        await _send_telegram_alert(f"🚨 サイト疎通異常\n{msg}")

    logger.info(f"nightly_site_check: {len(results) - len(failures)}/{len(results)} OK")


async def nightly_commit_review():
    """Tier 3-B: 深夜3:00 — 対象リポの直近24hコミットを diff レビュー。

    重大な指摘（security/performance）のみ Larry に通知。
    軽微な指摘は朝ブリーフィング用にサマリに集約する。
    """
    import subprocess

    logger.info("Running nightly_commit_review...")
    today_iso = date.today().isoformat()
    review_lines = ["\n## コミットレビュー (深夜3:00)\n"]
    serious_issues: list[tuple[str, str]] = []

    for repo_path in NIGHTLY_COMMIT_TARGETS:
        if not repo_path.exists():
            review_lines.append(f"- ⚠️ {repo_path.name}: パス未存在（スキップ）")
            continue

        # 独立 git repo か monorepo サブパスかで cwd と path 制限を切り替え
        has_own_git = (repo_path / ".git").exists()
        if has_own_git:
            cwd = str(repo_path)
            path_args: list[str] = []
        else:
            cwd = str(WORKSPACE_ROOT)
            try:
                rel = str(repo_path.relative_to(WORKSPACE_ROOT))
                path_args = ["--", rel]
            except ValueError:
                review_lines.append(
                    f"- ⚠️ {repo_path.name}: WORKSPACE_ROOT外（スキップ）"
                )
                continue

        try:
            log_result = await asyncio.to_thread(
                subprocess.run,
                ["git", "log", "--since=24 hours ago", "--oneline", *path_args],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=15,
            )
            commits = log_result.stdout.strip()
        except Exception as e:
            review_lines.append(
                f"- ⚠️ {repo_path.name}: git log失敗 ({type(e).__name__})"
            )
            continue

        if not commits:
            continue

        commit_count = len(commits.splitlines())
        review_lines.append(f"- 📝 {repo_path.name}: {commit_count} commit")

        try:
            diff_result = await asyncio.to_thread(
                subprocess.run,
                ["git", "log", "--since=24 hours ago", "-p", "--no-color", *path_args],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=20,
            )
            diff_text = diff_result.stdout[:50000]  # 大きい diff は切り捨て
        except Exception as e:
            review_lines.append(f"  - diff取得失敗: {type(e).__name__}")
            continue

        prompt = (
            f"以下は {repo_path.name} の過去24h diff です。"
            "重大なセキュリティ・パフォーマンス問題のみ簡潔に指摘してください"
            "（5行以内、無ければ「指摘なし」）。\n\n"
            f"{diff_text}"
        )
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["claude", "-p", "--output-format", "text"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=120,
            )
            review = (result.stdout or "").strip() or "(空応答)"
        except FileNotFoundError:
            review = "claude CLI未インストール"
        except Exception as e:
            review = f"レビュー失敗: {type(e).__name__}"

        review_lines.append(f"  - {review[:300]}")
        if (
            review
            and "指摘なし" not in review
            and "失敗" not in review
            and "未インストール" not in review
            and "(空応答)" not in review
        ):
            serious_issues.append((repo_path.name, review))

    NIGHTLY_QA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if NIGHTLY_QA_PATH.exists():
        existing = NIGHTLY_QA_PATH.read_text(encoding="utf-8")
    else:
        existing = f"# 夜間QA サマリ ({today_iso})\n\n"
    NIGHTLY_QA_PATH.write_text(
        existing + "\n".join(review_lines) + "\n", encoding="utf-8"
    )

    if serious_issues and _send_fn:
        lines = [f"🔍 **夜間コミットレビュー — 重大指摘 {len(serious_issues)}件**\n"]
        for name, issue in serious_issues:
            lines.append(f"### {name}\n{issue[:500]}\n")
        await _send_fn("開発-larry-product", "\n".join(lines))

    logger.info(f"nightly_commit_review: {len(serious_issues)} repos with issues")


# Tier 3-D: VPS ヘルスチェック（healthcheck.sh の report-only 結果を集約）
VPS_HOST = os.getenv("VPS_HOST", "root@46.250.252.99")
VPS_HEALTHCHECK_CMD = "HEALTHCHECK_REPORT_ONLY=1 bash /opt/apps/healthcheck.sh"


async def nightly_vps_health_check():
    """Tier 3-D: 深夜2:30 — VPS healthcheck.sh を report-only で叩いて夜間QAに集約。

    エラー（❌）があれば Jack に通知。警告（⚠️）のみなら通知せずサマリへ。
    """
    import subprocess

    logger.info("Running nightly_vps_health_check...")
    today_iso = date.today().isoformat()

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=15",
                VPS_HOST,
                VPS_HEALTHCHECK_CMD,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            output = f"⚠️ VPS healthcheck SSH失敗 (rc={result.returncode}): {result.stderr.strip()[:300]}"
            has_errors = True
        else:
            output = result.stdout.strip()
            has_errors = "❌" in output
    except Exception as e:
        output = f"⚠️ VPS healthcheck 実行エラー: {type(e).__name__}: {e}"
        has_errors = True

    # 夜間QAサマリへ追記（既存内容を保持）
    NIGHTLY_QA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if NIGHTLY_QA_PATH.exists():
        existing = NIGHTLY_QA_PATH.read_text(encoding="utf-8")
    else:
        existing = f"# 夜間QA サマリ ({today_iso})\n\n"

    section = f"\n## VPS ヘルスチェック (深夜2:30)\n\n```\n{output}\n```\n"
    NIGHTLY_QA_PATH.write_text(existing + section, encoding="utf-8")

    # エラーがあれば Jack に通知（警告のみなら朝ブリーフィングまで待つ）
    if has_errors and _send_fn:
        vps_msg = f"🚨 **VPS ヘルスチェック異常**\n\n```\n{output[:1500]}\n```"
        await _send_fn("運営-jack-operations", vps_msg)
        await _send_telegram_alert(f"🚨 VPS異常\n{output[:500]}")

    logger.info(f"nightly_vps_health_check: errors={has_errors}")


# Tier 3-E: launchd 生存確認 — ログ mtime とスケジュールから「沈黙ジョブ」検出
LAUNCHD_PLIST_DIR = Path.home() / "Library" / "LaunchAgents"
LAUNCHD_PLIST_PATTERN = "com.trustlink.*.plist"

# label → (max_age_seconds, label_for_summary) 上書き。Noneで監視除外
LAUNCHD_OVERRIDES: dict[str, Optional[int]] = {
    # ondemand-only / WatchPaths系: 監視しない
    "com.trustlink.wiki-daily-watch": None,
    "com.trustlink.wiki-git-sync": None,
    "com.trustlink.wiki-raw-watch": None,
    # white-bg: KeepAlive 常駐の image watcher。新規画像が無いとログを書かないので
    # mtime ベース判定不可（プロセス生存は launchctl 側で担保）。
    "com.trustlink.white-bg": None,
    # d-manager-dashboard: 月次更新でも問題ない用途
    "com.trustlink.d-manager-dashboard": 86400 * 14,
}


def _expected_max_age_seconds(d: dict) -> Optional[int]:
    """plist 定義から「ログがこの秒数より古かったら異常」の閾値を返す。Noneは判定不能=スキップ。"""
    if d.get("KeepAlive") is True:
        return 86400 * 7  # KeepAlive は厳密判定難しいので 7 日のみ
    interval = d.get("StartInterval")
    if interval:
        return max(int(interval) * 5, 600)  # 5倍 grace、最低 10 分
    cal = d.get("StartCalendarInterval")
    if cal:
        if isinstance(cal, list):
            cal = cal[0] if cal else {}
        if "Day" in cal:
            return 86400 * 33  # 月次
        if "Weekday" in cal:
            return 86400 * 9  # 週次
        if "Hour" in cal:
            return int(86400 * 1.5)  # 日次（36h）
    return None  # ondemand 等


def _get_launchctl_last_exit_code(label: str) -> Optional[int]:
    """`launchctl print gui/<uid>/<label>` から `last exit code` を取得.

    取得不能なら None を返す（沈黙判定で別途扱う）。
    """
    try:
        uid = os.getuid()
        result = subprocess.run(
            ["launchctl", "print", f"gui/{uid}/{label}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("last exit code = "):
                val = line.split("=", 1)[1].strip()
                # "(never exited)" の場合や数値以外は None
                try:
                    return int(val)
                except ValueError:
                    return None
        return None
    except Exception:
        return None


async def nightly_launchd_liveness_check():
    """Tier 3-E: 深夜4:00 — launchd 各ジョブの生存確認（ログ mtime + last exit code）。

    判定:
    - ログ mtime が期待値より古い → 沈黙ジョブ
    - last exit code != 0 → 失敗ジョブ（最近実行されたが異常終了）
    どちらかに該当すれば Jack に通知。
    """
    import plistlib

    logger.info("Running nightly_launchd_liveness_check...")
    today_iso = date.today().isoformat()

    plists = sorted(LAUNCHD_PLIST_DIR.glob(LAUNCHD_PLIST_PATTERN))
    now_ts = datetime.now().timestamp()

    silent: list[tuple[str, str, int]] = []  # (label, last_mtime_str, age_hours)
    failed: list[tuple[str, str, int]] = []  # (label, last_mtime_str, exit_code)
    skipped: list[str] = []
    healthy_count = 0
    rows: list[str] = []

    for plist_path in plists:
        try:
            with plist_path.open("rb") as f:
                d = plistlib.load(f)
        except Exception as e:
            logger.warning(f"Failed to parse {plist_path}: {e}")
            continue

        label = d.get("Label", plist_path.stem)
        max_age = LAUNCHD_OVERRIDES.get(label, "USE_DEFAULT")
        if max_age == "USE_DEFAULT":
            max_age = _expected_max_age_seconds(d)
        if max_age is None:
            skipped.append(label)
            continue

        # 最新の StandardOutPath / StandardErrorPath のいずれか新しい方を採用
        latest_mtime = 0
        for key in ("StandardOutPath", "StandardErrorPath"):
            p = d.get(key)
            if p and os.path.exists(p):
                latest_mtime = max(latest_mtime, os.path.getmtime(p))

        if latest_mtime == 0:
            # 月次/週次ジョブで初回実行前ならログがないのは正常
            cal = d.get("StartCalendarInterval")
            cal_first = cal[0] if isinstance(cal, list) and cal else cal
            is_periodic_unfired = isinstance(cal_first, dict) and (
                "Day" in cal_first or "Weekday" in cal_first
            )
            if is_periodic_unfired:
                rows.append(
                    f"- ⏳ **{label}**: ログなし（次回実行まで未起動・初回待ち）"
                )
                healthy_count += 1
                continue
            silent.append((label, "ログなし", -1))
            rows.append(
                f"- ❓ **{label}**: ログファイルなし（一度も実行されていない可能性）"
            )
            continue

        age_sec = now_ts - latest_mtime
        last_str = datetime.fromtimestamp(latest_mtime).strftime("%Y-%m-%d %H:%M")
        if age_sec > max_age:
            age_h = int(age_sec / 3600)
            max_h = int(max_age / 3600)
            silent.append((label, last_str, age_h))
            rows.append(
                f"- 🚨 **{label}**: 最終 {last_str} ({age_h}h前 / 期待値 {max_h}h以内)"
            )
            continue

        # mtime は新しい = 最近実行された。次に exit code を確認.
        # to_thread で同期 subprocess を別スレッドへ — event loop を止めない。
        exit_code = await asyncio.to_thread(_get_launchctl_last_exit_code, label)
        if exit_code is not None and exit_code != 0:
            failed.append((label, last_str, exit_code))
            rows.append(
                f"- 💥 **{label}**: 最終 {last_str} だが exit code = {exit_code}"
            )
        else:
            healthy_count += 1

    summary_block = (
        f"\n## launchd 生存確認 (深夜4:00)\n\n"
        f"healthy: {healthy_count}件 / silent: {len(silent)}件 / "
        f"failed: {len(failed)}件 / skipped: {len(skipped)}件\n\n"
    )
    if rows:
        summary_block += "\n".join(rows) + "\n"
    else:
        summary_block += "全ジョブ正常稼働中 ✅\n"

    NIGHTLY_QA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if NIGHTLY_QA_PATH.exists():
        existing = NIGHTLY_QA_PATH.read_text(encoding="utf-8")
    else:
        existing = f"# 夜間QA サマリ ({today_iso})\n\n"
    NIGHTLY_QA_PATH.write_text(existing + summary_block, encoding="utf-8")

    if (silent or failed) and _send_fn:
        parts: list[str] = []
        if failed:
            parts.append(f"💥 **launchd 失敗ジョブ検出 ({len(failed)}件)**")
            for label, last, ec in failed:
                parts.append(f"- **{label}**: 最終 {last} (exit={ec})")
        if silent:
            if parts:
                parts.append("")
            parts.append(f"🚨 **launchd 沈黙ジョブ検出 ({len(silent)}件)**")
            for label, last, age_h in silent:
                if age_h < 0:
                    parts.append(f"- **{label}**: ログなし")
                else:
                    parts.append(f"- **{label}**: 最終 {last} ({age_h}h前)")
        await _send_fn("運営-jack-operations", "\n".join(parts))

    logger.info(
        f"nightly_launchd_liveness_check: healthy={healthy_count} "
        f"silent={len(silent)} failed={len(failed)} skipped={len(skipped)}"
    )


async def nightly_token_expiry_check():
    """Tier 3-F: 深夜5:00 — 主要API トークンの期限・生存確認.

    対象: Threads (saimu-media + threads-auto), Meta Ads, Google Ads.
    残14日以下 or error なら Larry に通知。トークン値は外部に出さない.
    """
    import subprocess

    logger.info("Running nightly_token_expiry_check...")
    today_iso = date.today().isoformat()

    d_manager_root = Path(__file__).resolve().parent
    venv_python = d_manager_root / ".venv" / "bin" / "python"
    python_bin = str(venv_python) if venv_python.exists() else sys.executable

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [python_bin, "-m", "tools.token_expiry"],
            cwd=str(d_manager_root),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as e:
        output = f"⚠️ token_expiry 実行エラー: {type(e).__name__}: {e}"
        results: list[dict] = []
    else:
        try:
            data = json.loads(result.stdout) if result.stdout.strip() else {}
            results = data.get("results", [])
        except json.JSONDecodeError as e:
            results = []
            output = (
                f"⚠️ token_expiry JSON parse 失敗: {e}\nstderr: {result.stderr[:300]}"
            )
        else:
            output = ""

    rows: list[str] = []
    serious: list[dict] = []
    for r in results:
        name = r.get("name", "?")
        status = r.get("status", "?")
        if status == "ok":
            note = r.get("note") or f"残 {r.get('days_left')}日 ({r.get('expires_at')})"
            rows.append(f"- ✅ **{name}**: {note}")
        elif status == "warn":
            rows.append(
                f"- ⚠️ **{name}**: 残 {r.get('days_left')}日 ({r.get('expires_at')})"
            )
            serious.append(r)
        elif status == "error":
            rows.append(f"- 🚨 **{name}**: {r.get('error', 'unknown error')[:200]}")
            serious.append(r)
        else:  # skip
            rows.append(f"- ⏭️ **{name}**: {r.get('note', 'skipped')}")

    summary_block = "\n## API トークン期限・生存確認 (深夜5:00)\n\n"
    if rows:
        summary_block += "\n".join(rows) + "\n"
    elif output:
        summary_block += f"```\n{output}\n```\n"
    else:
        summary_block += "(結果なし)\n"

    NIGHTLY_QA_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = (
        NIGHTLY_QA_PATH.read_text(encoding="utf-8")
        if NIGHTLY_QA_PATH.exists()
        else f"# 夜間QA サマリ ({today_iso})\n\n"
    )
    NIGHTLY_QA_PATH.write_text(existing + summary_block, encoding="utf-8")

    if serious and _send_fn:
        lines = [f"🔑 **APIトークン警告 ({len(serious)}件)**\n"]
        for r in serious:
            name = r.get("name", "?")
            if r.get("status") == "warn":
                lines.append(
                    f"- **{name}**: 残 {r.get('days_left')}日 → {r.get('expires_at')} 切れ"
                )
            else:
                lines.append(f"- **{name}**: {r.get('error', 'error')[:200]}")
        token_msg = "\n".join(lines)
        await _send_fn("開発-larry-product", token_msg)
        await _send_telegram_alert(f"🔑 APIトークン警告\n{token_msg}")

    logger.info(
        f"nightly_token_expiry_check: {len(results)} checked, {len(serious)} alerts"
    )


async def nightly_discord_webhook_check():
    """Tier 3-G: 深夜5:30 — 主要 Discord Webhook の死活確認.

    GET で 404/401 を返す webhook を検出し Larry に通知。
    実体 URL は通知に出さず、ID と使用箇所のみ表示。
    """
    logger.info("Running nightly_discord_webhook_check...")
    today_iso = date.today().isoformat()

    d_manager_root = Path(__file__).resolve().parent
    venv_python = d_manager_root / ".venv" / "bin" / "python"
    python_bin = str(venv_python) if venv_python.exists() else sys.executable

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [python_bin, "-m", "tools.discord_webhook_check"],
            cwd=str(d_manager_root),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as e:
        logger.error(f"nightly_discord_webhook_check exec failed: {e}")
        return

    try:
        data = json.loads(result.stdout) if result.stdout.strip() else {}
    except json.JSONDecodeError as e:
        logger.warning(f"nightly_discord_webhook_check parse failed: {e}")
        data = {}

    results = data.get("results", [])
    rows: list[str] = []
    dead: list[dict] = []
    for r in results:
        status = r.get("status", "?")
        wid = r.get("id", "?")
        used = ", ".join(r.get("used_in", []))
        if status == "ok":
            rows.append(f"- ✅ **{wid}** ({r.get('name', '?')}) — {used}")
        elif status == "dead":
            dead.append(r)
            rows.append(f"- 💀 **{wid}** {r.get('error', '')} — {used}")
        else:
            rows.append(f"- ⚠️ **{wid}** {r.get('error', '')} — {used}")

    summary_block = (
        f"\n## Discord Webhook 死活 (深夜5:30)\n\n"
        f"checked: {len(results)} 件 / dead: {len(dead)} 件\n\n"
    )
    summary_block += "\n".join(rows) if rows else "(対象なし)\n"
    summary_block += "\n"

    NIGHTLY_QA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if NIGHTLY_QA_PATH.exists():
        existing = NIGHTLY_QA_PATH.read_text(encoding="utf-8")
    else:
        existing = f"# 夜間QA サマリ ({today_iso})\n\n"
    NIGHTLY_QA_PATH.write_text(existing + summary_block, encoding="utf-8")

    if dead and _send_fn:
        lines = [f"💀 **Discord Webhook 死活: 死んだ Webhook {len(dead)} 件**\n"]
        for r in dead:
            wid = r.get("id", "?")
            err = r.get("error", "")
            used = ", ".join(r.get("used_in", []))
            lines.append(f"- **{wid}** {err}\n  使用箇所: {used}")
        await _send_fn("運営-jack-operations", "\n".join(lines))

    logger.info(
        f"nightly_discord_webhook_check: {len(results)} checked, {len(dead)} dead"
    )


async def nightly_backup_integrity_check():
    """Tier 3-H: 深夜5:45 — VPS DB バックアップ整合性確認.

    /opt/backups/db/ 配下の REQUIRED ファイルが 24h 以内に更新されているか・
    サイズが極端に減っていないかを SSH 越しに検証.
    PENDING_SETUP（未バックアップ DB）も毎朝可視化のため記録する.
    """
    logger.info("Running nightly_backup_integrity_check...")
    today_iso = date.today().isoformat()

    d_manager_root = Path(__file__).resolve().parent
    venv_python = d_manager_root / ".venv" / "bin" / "python"
    python_bin = str(venv_python) if venv_python.exists() else sys.executable

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [python_bin, "-m", "tools.backup_integrity_check"],
            cwd=str(d_manager_root),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as e:
        logger.error(f"nightly_backup_integrity_check exec failed: {e}")
        return

    try:
        data = json.loads(result.stdout) if result.stdout.strip() else {}
    except json.JSONDecodeError as e:
        logger.warning(f"nightly_backup_integrity_check parse failed: {e}")
        data = {}

    ssh_error = data.get("ssh_error")
    required = data.get("required", [])
    pending = data.get("pending_setup", [])

    rows: list[str] = []
    problems: list[dict] = []
    if ssh_error:
        rows.append(f"- 💥 SSH 接続失敗: {ssh_error}")
    else:
        for r in required:
            label = r.get("label", r.get("name", "?"))
            status = r.get("status")
            if status == "ok":
                age = r.get("age_hours", "?")
                size = r.get("size_bytes", 0)
                rows.append(f"- ✅ **{label}** ({age}h前 / {size:,}B)")
            else:
                problems.append(r)
                err = r.get("error", "")
                marker = "💀" if status == "missing" else "⚠️"
                rows.append(f"- {marker} **{label}** {status}: {err}")
        for p in pending:
            label = p.get("label", p.get("name", "?"))
            status = p.get("status")
            if status == "ok":
                age = p.get("age_hours", "?")
                rows.append(f"- ✅ **{label}** ({age}h前) — 整備済み")
            else:
                rows.append(f"- 🔧 **{label}** — backup.sh 未対応（要整備）")

    summary_block = (
        f"\n## DB バックアップ整合性 (深夜5:45)\n\n"
        f"required: {len(required)} 件 / problems: {len(problems)} 件 / "
        f"pending_setup: {len(pending)} 件\n\n"
    )
    summary_block += "\n".join(rows) if rows else "(対象なし)\n"
    summary_block += "\n"

    NIGHTLY_QA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if NIGHTLY_QA_PATH.exists():
        existing = NIGHTLY_QA_PATH.read_text(encoding="utf-8")
    else:
        existing = f"# 夜間QA サマリ ({today_iso})\n\n"
    NIGHTLY_QA_PATH.write_text(existing + summary_block, encoding="utf-8")

    if (problems or ssh_error) and _send_fn:
        lines = ["💀 **DB バックアップ整合性: 異常検知**\n"]
        if ssh_error:
            lines.append(f"- SSH error: {ssh_error}")
        for p in problems:
            label = p.get("label", p.get("name", "?"))
            status = p.get("status", "?")
            err = p.get("error", "")
            lines.append(f"- **{label}** [{status}] {err}")
        await _send_fn("運営-jack-operations", "\n".join(lines))

    logger.info(
        f"nightly_backup_integrity_check: required={len(required)} "
        f"problems={len(problems)} pending={len(pending)} ssh_error={bool(ssh_error)}"
    )


async def nightly_sns_posting_check():
    """Tier 3-I: 深夜6:00 — SNS 0 投稿アラート (saimu-media Threads).

    過去 24h で「✅ Threads投稿完了」が 0 件なら Discord 通知.
    threads-auto / faxcel-x-auto は本実装ではスコープ外.
    """
    logger.info("Running nightly_sns_posting_check...")
    today_iso = date.today().isoformat()

    d_manager_root = Path(__file__).resolve().parent
    venv_python = d_manager_root / ".venv" / "bin" / "python"
    python_bin = str(venv_python) if venv_python.exists() else sys.executable

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [python_bin, "-m", "tools.sns_posting_check"],
            cwd=str(d_manager_root),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as e:
        logger.error(f"nightly_sns_posting_check exec failed: {e}")
        return

    try:
        data = json.loads(result.stdout) if result.stdout.strip() else {}
    except json.JSONDecodeError as e:
        logger.warning(f"nightly_sns_posting_check parse failed: {e}")
        data = {}

    results = data.get("results", [])
    rows: list[str] = []
    problems: list[dict] = []
    for r in results:
        label = r.get("label", r.get("name", "?"))
        status = r.get("status")
        if status == "ok":
            count = r.get("posts_24h", 0)
            rows.append(f"- ✅ **{label}** — 24h 投稿数: {count}")
        elif status == "zero_posts":
            problems.append(r)
            count = r.get("posts_24h", 0)
            rows.append(f"- 🚨 **{label}** — 24h 投稿数: {count}（0件アラート）")
        else:
            problems.append(r)
            err = r.get("error", "")
            rows.append(f"- 💥 **{label}** error: {err}")

    summary_block = (
        f"\n## SNS 0 投稿アラート (深夜6:00)\n\n"
        f"checked: {len(results)} 件 / problems: {len(problems)} 件\n\n"
    )
    summary_block += "\n".join(rows) if rows else "(対象なし)\n"
    summary_block += "\n"

    NIGHTLY_QA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if NIGHTLY_QA_PATH.exists():
        existing = NIGHTLY_QA_PATH.read_text(encoding="utf-8")
    else:
        existing = f"# 夜間QA サマリ ({today_iso})\n\n"
    NIGHTLY_QA_PATH.write_text(existing + summary_block, encoding="utf-8")

    if problems and _send_fn:
        lines = [f"🚨 **SNS 0 投稿アラート: {len(problems)} 件**\n"]
        for p in problems:
            label = p.get("label", p.get("name", "?"))
            status = p.get("status", "?")
            err = p.get("error", "")
            lines.append(f"- **{label}** [{status}] {err}")
        await _send_fn("運営-jack-operations", "\n".join(lines))

    logger.info(
        f"nightly_sns_posting_check: {len(results)} checked, {len(problems)} problems"
    )


async def d_manager_heartbeat():
    """Tier 3-J: d-manager 死亡検知用ハートビート (10分毎).

    SSH 越しに VPS の /opt/heartbeat/d-manager.txt を touch する.
    VPS 側 cron (*/15 min) がこのファイルの mtime を見て古ければ Telegram 警告.

    SSH 失敗時もログだけ出して例外は飲む (このジョブの失敗で scheduler を止めない).
    """
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=5",
                "root@46.250.252.99",
                "mkdir -p /opt/heartbeat && touch /opt/heartbeat/d-manager.txt",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            logger.warning(
                "d_manager_heartbeat ssh failed: rc=%d stderr=%s",
                result.returncode,
                result.stderr.strip()[:200],
            )
    except Exception as e:
        logger.warning("d_manager_heartbeat exception: %s: %s", type(e).__name__, e)


def _read_obsidian_context() -> str:
    """朝ブリーフィング用に Obsidian から積み残しタスクとプロダクト状況を読む。"""
    import yaml as _yaml

    JST = timezone(timedelta(hours=9))
    yesterday = datetime.now(JST).date() - timedelta(days=1)
    obsidian_dir = Path.home() / "Obsidian"
    output_lines: list[str] = []

    # 1. 昨日のdaily note → Tomorrow Next の未完タスク
    daily_path = obsidian_dir / "Daily" / f"{yesterday}.md"
    if daily_path.exists():
        try:
            content = daily_path.read_text(encoding="utf-8")
            match = re.search(r"## Tomorrow Next\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
            if match:
                unchecked = [
                    line.strip()
                    for line in match.group(1).splitlines()
                    if line.strip().startswith("- [ ]")
                ]
                if unchecked:
                    output_lines.append("【積み残しタスク（昨日のTomorrow Next）】")
                    output_lines.extend(unchecked)
        except Exception as e:
            logger.warning("_read_obsidian_context: daily note read failed: %s", e)

    # 2. wiki/products/ → type:product かつ status:active のページ
    products_dir = obsidian_dir / "wiki" / "products"
    if products_dir.exists():
        product_lines: list[str] = []
        for md_file in sorted(products_dir.glob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8")
                if not text.startswith("---"):
                    continue
                end = text.find("---", 3)
                if end == -1:
                    continue
                fm = _yaml.safe_load(text[3:end])
                if not isinstance(fm, dict):
                    continue
                if fm.get("type") != "product" or fm.get("status") != "active":
                    continue
                name = fm.get("title", md_file.stem)
                na = fm.get("next_action") or "未設定"
                issues = fm.get("issues") or "なし"
                product_lines.append(f"  • {name}: next={na} / issues={issues}")
            except Exception as e:
                logger.warning(
                    "_read_obsidian_context: %s parse failed: %s", md_file.name, e
                )
        if product_lines:
            output_lines.append("\n【プロダクト状況（active）】")
            output_lines.extend(product_lines)

    return "\n".join(output_lines)


def _read_nightly_qa_summary() -> str:
    """Tier 3-C: 朝ブリーフィングで使う夜間QAサマリを読む。当日分のみ。"""
    if not NIGHTLY_QA_PATH.exists():
        return ""
    try:
        content = NIGHTLY_QA_PATH.read_text(encoding="utf-8")
        today_iso = date.today().isoformat()
        if today_iso not in content:
            return ""  # 古いキャッシュは無視
        return content
    except Exception as e:
        logger.warning(f"_read_nightly_qa_summary failed: {e}")
        return ""


# --- Department morning reports ---

DEPT_REPORT_PROMPTS = {
    "operations": (
        "Jack",
        "運営-jack-operations",
        "おはようございます。eBay運営の朝レポートをお願いします。"
        "以下のKPIデータを元に、売上状況・在庫アラート・今日の優先アクションを報告してください。"
        "短く要点のみ（5行以内）で。\n\n{kpi_data}",
    ),
    "marketing": (
        "Mark",
        "マーケティング-mark-marketing",
        "おはようございます。マーケティングの朝レポートをお願いします。"
        "以下のデータを元に、Threads運用状況・エンゲージメント・今日のアクションを報告してください。"
        "短く要点のみ（5行以内）で。\n\n{kpi_data}",
    ),
}


_NEWS_QUERIES_EN = [
    "Claude Anthropic AI",
    "Google Gemini AI",
    "ChatGPT OpenAI",
    "AI monetization business 2026",
]
_NEWS_QUERIES_JA = [
    "AI 最新ニュース",
    "生成AI ビジネス活用",
]
_NEWS_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _rss_fetch(query: str, lang: str = "en", num: int = 6) -> list[dict]:
    if lang == "ja":
        url = (
            f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}"
            "&hl=ja&gl=JP&ceid=JP:ja"
        )
    else:
        url = (
            f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}"
            "&hl=en&gl=US&ceid=US:en"
        )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _NEWS_UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            root = ET.fromstring(resp.read())
        items = []
        for item in root.findall(".//item")[:num]:
            items.append(
                {
                    "title": item.findtext("title", ""),
                    "link": item.findtext("link", ""),
                    "desc": unescape(
                        re.sub(r"<[^>]+>", "", item.findtext("description", ""))
                    )[:300],
                    "date": item.findtext("pubDate", ""),
                }
            )
        return items
    except Exception as e:
        logger.warning(f"RSS fetch failed ({query}): {e}")
        return []


def _collect_news() -> str:
    sections = []
    for q in _NEWS_QUERIES_EN:
        items = _rss_fetch(q, lang="en")
        if items:
            lines = [f"### {q}"]
            for it in items:
                lines.append(
                    f"- {it['title']} ({it['date']})\n  {it['desc']}\n  {it['link']}"
                )
            sections.append("\n".join(lines))
    for q in _NEWS_QUERIES_JA:
        items = _rss_fetch(q, lang="ja")
        if items:
            lines = [f"### {q}"]
            for it in items:
                lines.append(
                    f"- {it['title']} ({it['date']})\n  {it['desc']}\n  {it['link']}"
                )
            sections.append("\n".join(lines))
    return "\n\n".join(sections)


def _summarize_news(raw: str, today_iso: str) -> str:
    import anthropic as _anthropic

    client = _anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system=(
            "あなたはAI業界専門のニュースキュレーターです。"
            "提供された検索結果を元に、日本語でAIデイリーダイジェストを作成してください。\n"
            "## フォーマット\n"
            f"# AIニュース {today_iso}\n\n"
            "## ハイライト（3行）\n\n"
            "## Claude / Anthropic（最新2-3件、日付・内容・意義）\n\n"
            "## Google / Gemini（同上）\n\n"
            "## OpenAI（同上）\n\n"
            "## 日本のAI動向（2-3件）\n\n"
            "## AIマネタイズ最前線（2件）\n\n"
            "---\nSources: （使用URLリスト）\n\n"
            "## ルール: 検索結果に無い情報は書かない。各ニュースに日付を明記。"
        ),
        messages=[
            {"role": "user", "content": f"以下を元にダイジェストを作成:\n\n{raw}"}
        ],
    )
    return msg.content[0].text


async def fetch_ai_news_cache() -> None:
    """07:00 JST — Google News RSSを取得・Haikuで要約してnews_cacheに保存。"""
    today_iso = date.today().isoformat()
    cache_dir = config.COMPANY_DIR / "secretary" / "news_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{today_iso}.md"

    if cache_path.exists():
        logger.info("fetch_ai_news_cache: already exists, skip")
        return

    loop = asyncio.get_running_loop()
    raw = await loop.run_in_executor(None, _collect_news)
    if len(raw) < 100:
        logger.warning("fetch_ai_news_cache: too few results, abort")
        return

    digest = await loop.run_in_executor(None, _summarize_news, raw, today_iso)
    cache_path.write_text(digest, encoding="utf-8")
    logger.info(f"fetch_ai_news_cache: saved {cache_path} ({len(digest)} chars)")


async def morning_briefing():
    """Generate and send morning briefing + task board."""
    logger.info("Running morning briefing...")

    # 0. Tier 3-C: 夜間QA サマリを先頭に表示（あれば）
    nightly_summary = _read_nightly_qa_summary()
    if nightly_summary and _send_fn:
        await _send_fn("ceo-steve-general", nightly_summary)
        logger.info("Nightly QA summary sent")

    # 0-b: 昨日のメール下書き集計（カウンタをスナップ → 0にリセット）
    draft_stats = _reset_email_draft_stats()
    draft_report = _format_email_draft_daily_report(draft_stats)
    if draft_report and _send_fn:
        await _send_fn("ceo-steve-general", draft_report)
        logger.info("Email draft daily report sent")

    # 1. Task board with buttons to CEOチャンネル
    tasks = _parse_active_tasks()
    task_board = _build_task_board()
    if _send_fn:
        view = _task_view_fn(tasks) if _task_view_fn and tasks else None
        await _send_fn("ceo-steve-general", task_board, view)
    logger.info("Task board sent")

    # 2. Send tasks to each department channel
    dept_tasks = {}
    for t in tasks:
        owner = t["owner"]
        dept_tasks.setdefault(owner, []).append(t)

    for owner, task_list in dept_tasks.items():
        channel = DEPT_CHANNELS.get(owner)
        if channel and channel != "ceo-steve-general":
            lines = [f"📋 **{owner}の今日のタスク**\n"]
            for t in task_list:
                age = f"（{t['age_days']}日経過）" if t["age_days"] >= 3 else ""
                deadline = (
                    f" 🔥期限: {t['deadline']}" if t["deadline"] != "なし" else ""
                )
                state_icon = {"UN": "⚪", "IN": "🔵", "BL": "🟣"}.get(t["state"], "⚪")
                lines.append(
                    f"- [{t['state']}] {state_icon} {t['name']}{deadline}{age}"
                )
            if _send_fn:
                view = _task_view_fn(task_list) if _task_view_fn and task_list else None
                await _send_fn(channel, "\n".join(lines), view)

    # 3. Dream briefing to CEOチャンネル
    dream_summary = get_dream_briefing()
    if dream_summary and _send_fn:
        await _send_fn("ceo-steve-general", dream_summary)
    logger.info("Dream briefing sent")

    # 4. 占術指針を先にDiscordに直接送信（AIを経由しない）
    divination = get_daily_summary()
    if date.today().day == 1:
        divination += "\n\n" + get_monthly_summary()
    if _send_fn:
        await _send_fn("ceo-steve-general", divination)
    logger.info("Divination sent")

    # 5. AI briefing (Steve) — 拡張版: メール返信下書き + 商談リサーチ参照 + TODO自動抽出
    obsidian_ctx = _read_obsidian_context()
    obsidian_section = (
        f"\n\n## Obsidianダッシュボード\n{obsidian_ctx}" if obsidian_ctx else ""
    )
    teaching = _pick_daily_teaching()
    today_iso = date.today().isoformat()
    news_cache_path = (
        config.COMPANY_DIR / "secretary" / "news_cache" / f"{today_iso}.md"
    )
    research_dir = config.COMPANY_DIR / "secretary" / "research"
    todos_path = config.COMPANY_DIR / "secretary" / "todos" / "active.md"

    briefing_prompt = (
        f"おはようございます。朝のブリーフィングをお願いします。\n\n"
        "## 必須実行項目\n"
        "1. **カレンダー予定**: Googleカレンダーで本日の予定を全て取得\n"
        "2. **未読メール**: Gmail未読を全件確認\n"
        "   - 返信が必要なメールについて、空き時間込みの返信下書きをGmail下書きに自動作成\n"
        "   - 返信不要・購読系・通知系は除外\n"
        "3. **TODO抽出**: 未読メール本文から「やるべきこと」を抽出し、新規タスクとして "
        f"{todos_path} に追記（既存タスクと重複しないこと）\n"
        "4. **TODO（昨日の持ち越し含む）**: 期限切れ・放置タスクを優先表示\n"
        "5. **商談前リサーチ**: 本日のミーティング予定がある場合、"
        f"{research_dir}/{today_iso}_*.md を全て Read で読み、要点を3行で報告\n"
        "6. **情報収集（任意）**: 以下のファイルが存在すれば内容を読み、注目トピックを1-2件紹介\n"
        f"   - {news_cache_path}\n"
        "7. **空き時間活用提案**\n\n"
        f"## 今日の教え\n{teaching}"
        f"{obsidian_section}\n\n"
        "## ルール\n"
        "- メール下書き作成・TODO追記の件数は明示的に報告すること\n"
        "- 各ファイルが存在しない場合は『○○なし』と1行で言及\n"
        "- データ取得失敗があれば社訓2に従い明示\n"
        "- 全体は10行以内に圧縮"
    )
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        process_message,
        briefing_prompt,
        "secretary",
        "scheduler-briefing",
    )
    # 前日のダイジェストサマリ（知見エンジン フェーズ1）
    try:
        import datetime as _dt

        from knowledge import store as kstore

        yday = (_dt.date.today() - _dt.timedelta(days=1)).strftime("%Y-%m-%d")
        drows = kstore.get_digests(config.KNOWLEDGE_DB_PATH, yday)
        if drows:
            topics = []
            for r in drows:
                if r["topics_json"]:
                    import json as _json

                    topics.extend(_json.loads(r["topics_json"]))
            uniq = list(dict.fromkeys(topics))[:5]
            line = f"\n\n📋 昨日のダイジェスト {len(drows)}件"
            if uniq:
                line += "｜主なトピック: " + " / ".join(uniq)
            result = (result or "") + line
    except Exception:  # noqa: BLE001
        logger.exception("morning_briefing: digest summary failed")
    if _send_fn:
        await _send_fn("ceo-steve-general", result)
    logger.info("Morning briefing sent")

    # 6. Department KPI reports (部門別朝レポート)
    kpi = _collect_kpi()
    for dept, kpi_data in kpi.items():
        prompt_info = DEPT_REPORT_PROMPTS.get(dept)
        if not prompt_info:
            continue
        char_name, channel, prompt_template = prompt_info
        prompt = prompt_template.format(kpi_data=kpi_data)
        try:
            dept_result = await loop.run_in_executor(
                None, process_message, prompt, dept, f"scheduler-kpi-{dept}"
            )
            if _send_fn:
                await _send_fn(channel, dept_result)
            logger.info(f"KPI report sent: {dept} → {channel}")
        except Exception as e:
            logger.error(f"KPI report failed for {dept}: {e}")


async def evening_review():
    """Evening review — TODO summary + Obsidian Daily Note の秘書ログを更新する。"""
    logger.info("Running evening review...")

    # Increment skip counts for tasks not completed today
    _increment_skip_counts()

    # Build evening summary
    tasks = _parse_active_tasks()
    stale = [t for t in tasks if t["skip_count"] >= 3]

    if stale:
        lines = ["⚠️ **3回以上スキップされたタスク — 判断してください**\n"]
        for t in stale:
            lines.append(
                f"🗑️ **{t['name']}** → {t['owner']}（{t['age_days']}日経過、{t['skip_count']}回スキップ）"
            )
            lines.append(
                f"  → 「やる」「捨てる」「来週に延期」のどれかを返信してください\n"
            )
        if _send_fn:
            await _send_fn("ceo-steve-general", "\n".join(lines))

    # AI review — 秘書ログをObsidianに直接書き込む + memory への昇格
    today_iso = date.today().isoformat()
    obsidian_path = str(Path.home() / "Obsidian" / "Daily" / f"{today_iso}.md")
    raw_path = str(
        config.COMPANY_DIR / "secretary" / "memory" / "raw" / f"{today_iso}.md"
    )
    prompt = (
        "今日の振り返り（夕レビュー）を以下の手順で実行してください。\n\n"
        "## 手順\n"
        "1. 今日のカレンダー予定を確認（実施済みのMTG/商談）\n"
        "2. 今日のTODO完了率・未完了の持ち越し対象を確認\n"
        "3. 今日の主要メールやり取りを要約（Gmailで本日分を確認）\n"
        "4. 未完了タスクの明日への持ち越し提案\n"
        "5. 明日の予定プレビュー\n"
        "6. **Obsidian Daily Noteへ追記**: tools/daily_note.py の upsert_secretary_section() を Bash 経由で実行する。\n"
        f"   - ファイル: {obsidian_path}\n"
        "   - 「## 🤵 秘書ログ」セクションに以下のフォーマットで記入:\n"
        "     ### 今日のMTG\n"
        "     ### TODO完了率\n"
        "     ### 主要メール\n"
        "     ### 持ち越し\n"
        "     ### 明日の予定プレビュー\n"
        "7. **メモリーの昇格（重要）**: tools/memory.py を使って3階層メモリーに学びを保存する。\n"
        f"   - 当日のローデータ: {raw_path} を Read で確認（存在すれば）\n"
        "   - 重要な事実は upsert_fact(topic, fact) で facts/ に保存\n"
        "   - 再利用可能な学び・気づきは upsert_digest(topic, learning) で digest/ に保存\n"
        "   - 例: digest/メール返信.md, digest/商談準備.md, digest/ロキ_好み.md\n\n"
        "## 完了報告\n"
        "Discordには要約（5-7行）のみ返答すること。詳細はObsidianを参照と書く。\n"
        "Obsidianへの書き込みが失敗した場合は明示的に報告する（社訓2「出来ぬなら出来ぬと言え」）。"
    )
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        process_message,
        prompt,
        "secretary",
        "scheduler-review",
    )
    if _send_fn:
        await _send_fn("ceo-steve-general", result)
    logger.info("Evening review sent")


async def pre_meeting_research():
    """夕方20:30 — 翌日のミーティング/商談を検出し、相手と過去経緯を事前リサーチする。

    結果は `.company/secretary/research/YYYY-MM-DD_<案件>.md` に保存し、
    人物DBにも接触履歴を追記する。翌朝のブリーフィングで参照される。
    """
    logger.info("Running pre-meeting research...")
    research_dir = config.COMPANY_DIR / "secretary" / "research"
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    prompt = (
        f"明日（{tomorrow}）のミーティング/商談を事前リサーチしてください。\n\n"
        "## 手順\n"
        f"1. Googleカレンダーで {tomorrow} の予定を全て取得\n"
        "2. ミーティング/商談系の予定（タイトルに『打合せ』『MTG』『商談』『面談』等を含む、または参加者2名以上）を抽出\n"
        "3. 各ミーティングについて以下を実行:\n"
        "   a. 参加者名・会社名を特定\n"
        "   b. Gmail で過去の関連メールを検索（差出人・件名・宛先）\n"
        "   c. Discord の関連チャンネルで過去のやり取りを検索（運営/開発/マーケ等）\n"
        "   d. Web検索で会社/人物の最新情報を取得\n"
        "   e. レポートを以下のパスに保存:\n"
        f"      {research_dir}/{tomorrow}_<案件名>.md\n"
        "      内容: 想定アジェンダ・過去の経緯・相手の関心事・準備すべきこと\n"
        "   f. 人物DBを更新: tools/people_db.py の upsert_person() で接触履歴に追記\n"
        "4. リサーチ完了後、Discord には件数のみ要約（5行以内）で報告\n\n"
        "## ルール\n"
        "- ミーティングが1件もない場合: 「明日はミーティング予定なし」と1行で返す\n"
        "- 取得失敗があれば社訓2に従い「○○が取れませんでした」と明示\n"
        "- データを推測で埋めない"
    )
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        process_message,
        prompt,
        "research",
        "scheduler-pre-meeting",
    )
    if _send_fn:
        await _send_fn(
            "ceo-steve-general", f"🔎 **明日のミーティング事前リサーチ**\n\n{result}"
        )
    logger.info("Pre-meeting research sent")


async def news_collection():
    """朝7:00 — ニュースレターを収集・要約してキャッシュする。

    結果は `.company/secretary/news_cache/YYYY-MM-DD.md` に保存し、
    morning_briefing がプロンプトで参照する。
    AI系ニュースは fetch_ai_news_cache（Google News RSS）が別途担当。
    """
    logger.info("Running news collection...")
    cache_dir = config.COMPANY_DIR / "secretary" / "news_cache"
    today_iso = date.today().isoformat()
    cache_path = cache_dir / f"{today_iso}.md"

    prompt = (
        "今朝のニュースレター収集をお願いします。\n\n"
        "## 収集対象\n"
        "1. **ニュースレター要約**: Gmailで Newsletter / List-Unsubscribe ヘッダ付きまたは"
        "「ニュースレター」「メルマガ」ラベルのメールから、過去24時間の重要トピックを5件抽出\n\n"
        "## 出力先\n"
        f"{cache_path} が既に存在する場合は末尾に追記、なければ新規作成:\n"
        "---\ndate: YYYY-MM-DD\n---\n\n"
        "## 📧 ニュースレター要約\n（5件・差出人と件名）\n\n"
        "## ルール\n"
        "- メールが0件なら「本日のニュースレターなし」と1行記載\n"
        "- 推測で埋めない・社訓1遵守\n"
        "- Discordには件数のみ要約（2行以内）で報告"
    )
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        process_message,
        prompt,
        "research",
        "scheduler-news",
    )
    if _send_fn:
        await _send_fn("日報-daily-digest", f"📰 **朝の情報収集**\n\n{result}")
    logger.info("News collection sent")


async def dream_checkin():
    """Weekly dream check-in — ask about dreams, review pyramid balance."""
    logger.info("Running dream check-in...")

    # Get current dream state for context
    pyramid = get_pyramid_summary()
    dream_list = list_dreams()

    prompt = (
        "週に1回の「夢チェックイン」の時間です。以下のルールで社長に話しかけてください。\n\n"
        "## ルール\n"
        "- 親しみのあるトーンで、夢について対話を促す\n"
        "- 現在の夢リストとピラミッドの状態を踏まえて話す\n"
        "- 以下のうち状況に合うものを1〜2個だけ聞く（全部聞かない）:\n"
        "  1. 最近新しくやりたいと思ったことはあるか？\n"
        "  2. 登録済みの夢で進捗があったものはあるか？\n"
        "  3. ピラミッドで空の分野があれば、その分野で興味あることを軽く聞く\n"
        "  4. 優先度Aの夢について、今週何か動けたか聞く\n"
        "- 短く（5行以内）、プレッシャーにならない聞き方で\n"
        "- 「夢を追加して」「進捗更新して」と返せば対応できることを自然に伝える\n\n"
        f"## 現在の夢リスト\n{dream_list}\n\n"
        f"## ピラミッド\n{pyramid}"
    )

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, process_message, prompt, "secretary", "scheduler-dream-checkin"
    )
    if _send_fn:
        await _send_fn("ceo-steve-general", result)
    logger.info("Dream check-in sent")


def _fetch_vps_log(remote_path: str) -> str:
    """Fetch a log file from VPS via SSH."""
    import subprocess as _sp

    vps_host = os.getenv("VPS_HOST", "root@46.250.252.99")
    try:
        result = _sp.run(
            ["ssh", "-o", "ConnectTimeout=10", vps_host, f"cat {remote_path}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout if result.returncode == 0 else ""
    except Exception as e:
        logger.warning(f"VPS log fetch failed ({remote_path}): {e}")
        return ""


async def ad_report_analysis():
    """Read ad report logs (via SSH if needed) and have Mark provide strategic analysis."""
    logger.info("Running ad report analysis...")

    # Try local paths first (Docker mount), then SSH
    meta_local = Path("/root/marketing/meta-ads/exports/cron.log")
    google_local = Path("/root/marketing/google-ads/cron.log")

    log_sources = [
        ("Meta Ads", meta_local, "/root/marketing/meta-ads/exports/cron.log"),
        ("Google Ads", google_local, "/root/marketing/google-ads/cron.log"),
    ]

    reports = []
    today = date.today()
    dates_to_check = [(today - timedelta(days=i)).isoformat() for i in range(3)]

    for name, local_path, remote_path in log_sources:
        # Local first, SSH fallback
        if local_path.exists():
            content = local_path.read_text(encoding="utf-8")
        else:
            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(None, _fetch_vps_log, remote_path)

        if not content:
            continue

        blocks = content.split("日次レポート生成")
        if len(blocks) >= 2:
            latest = blocks[-1]
            if any(d in latest for d in dates_to_check):
                reports.append(f"## {name} レポート\n{latest[:3000]}")

    if not reports:
        logger.info("No ad reports found for today, skipping analysis")
        return

    report_data = "\n\n".join(reports)

    prompt = (
        "広告日報が届きました。以下のデータを分析して戦略的な提案をしてください。\n\n"
        "## 分析ルール\n"
        "- Facebook vs Google の統合比較（CPA・CVR・ROAS）\n"
        "- 各プラットフォームの緊急課題を特定\n"
        "- 具体的な戦略提案（予算配分変更、クリエイティブ改善、停止すべき広告）\n"
        "- 社長決裁が必要な案件は明示する\n"
        "- 短く要点のみ。数値で語る。\n\n"
        f"{report_data}"
    )

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, process_message, prompt, "marketing", "scheduler-ad-analysis"
    )
    if _send_fn:
        await _send_fn("マーケティング-mark-marketing", result)
    logger.info("Ad report analysis sent")


async def weekly_review():
    """Generate and send weekly review."""
    logger.info("Running weekly review...")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        process_message,
        "週次レビューをお願いします。今週のTODO完了状況、来週の予定プレビュー、経費サマリーをまとめてください。",
        "strategy",
        "scheduler-weekly",
    )
    if _send_fn:
        await _send_fn("戦略-reid-strategy", result)

    # 学習ループ: スキル棚卸し + 会話ログのプルーニング
    learning_prune()
    try:
        await learning_curate()
    except Exception:  # noqa: BLE001
        logger.exception("weekly_review: learning_curate failed")


async def strategic_proposal():
    """毎週日曜19:00 — Reid が事業全体を俯瞰し、課題・改善・企画提案を自発的に上げる。"""
    logger.info("Running strategic_proposal...")
    JST_NOW = datetime.now(JST)
    today = JST_NOW.strftime("%Y-%m-%d")

    kpi = _collect_kpi()
    kpi_text = (
        "\n".join(f"【{dept}】\n{data}" for dept, data in kpi.items())
        if kpi
        else "（KPIデータ取得なし）"
    )

    result = subprocess.run(
        ["git", "-C", str(Path.home() / "Claude-Workspace"), "log", "--oneline", "-20"],
        capture_output=True,
        text=True,
    )
    recent_commits = result.stdout.strip() or "（コミット取得なし）"

    prompt = f"""あなたは事業戦略担当 Reid です。今週の事業状況を俯瞰し、
経営者 Hiro に「自発的な提案」を 3〜5 件上げてください。

## 今日の日付
{today}

## 直近のコード変更（git log）
{recent_commits}

## KPI サマリー
{kpi_text}

## 提案の観点（いずれか1つ以上を含む）
- 売上・利益を上げる企画（新施策・改善）
- 運用コストを下げる改善（自動化・削除）
- リスク・課題の早期警告
- 競合・市場変化への対応

## 出力フォーマット
🧠 **今週の戦略提案** — {today}

**提案 1: [タイトル]**
背景: [なぜ今これが必要か]
提案内容: [具体的なアクション]
期待効果: [何が変わるか]
優先度: 🔴高 / 🟡中 / 🟢低

[提案 2〜5 同様]

⚡ **今週のアクション候補（TOP 1）**
[最も優先度が高い1件を1〜2行で]
"""
    loop = asyncio.get_event_loop()
    result_text = await loop.run_in_executor(
        None,
        process_message,
        prompt,
        "strategy",
        "scheduler:strategic-proposal",
    )
    if _send_fn:
        await _send_fn("戦略-reid-strategy", result_text)
    logger.info("Strategic proposal sent")


async def learning_review():
    """夜間バッチ: 未レビューのセッション（チャンネル+日付）を振り返り、.company/ を更新する。"""
    if not config.LEARNING_REVIEW_ENABLED:
        logger.info("learning_review: disabled (LEARNING_REVIEW_ENABLED=false), skip")
        return
    logger.info("Running learning_review...")
    from learning import reviewer, store

    db = config.LEARNING_DB_PATH
    company = config.COMPANY_DIR
    store.init_db(db)
    requeued = store.requeue_stuck(db, stuck_minutes=config.LEARNING_STUCK_MINUTES)
    if requeued:
        logger.info("learning_review: requeued %d stuck sessions", requeued)
    skipped = store.mark_short_skipped(db, min_turns=config.LEARNING_MIN_TURNS)
    pending = store.list_pending_reviews(
        db,
        min_turns=config.LEARNING_MIN_TURNS,
        max_age_days=config.LEARNING_REVIEW_MAX_AGE_DAYS,
    )[: config.LEARNING_MAX_PER_RUN]

    results = []
    for sess in pending:
        try:
            res = reviewer.run_review(
                db_path=db,
                company_dir=company,
                channel_id=sess["channel_id"],
                review_date=sess["review_date"],
                channel_name=sess.get("channel_name") or sess["channel_id"],
                department=sess.get("department") or "secretary",
                model=config.REVIEW_MODEL_CLI,
                dryrun=config.LEARNING_REVIEW_DRYRUN,
                allowed_tools=config.LEARNING_ALLOWED_TOOLS,
                dryrun_allowed_tools=config.LEARNING_DRYRUN_ALLOWED_TOOLS,
                disallowed_tools=config.LEARNING_DISALLOWED_TOOLS,
                char_limit=config.LEARNING_CONTEXT_CHAR_LIMIT,
                timeout_sec=config.LEARNING_REVIEW_TIMEOUT_SEC,
                skill_hits_path=config.SKILL_HITS_PATH,
            )
            results.append((sess, res))
        except Exception:  # noqa: BLE001
            logger.exception(
                "learning_review: run_review failed for %s/%s",
                sess["channel_id"],
                sess["review_date"],
            )
            results.append(
                (sess, {"status": "error", "note": "exception", "out_of_bounds": []})
            )

    # 通知メッセージを組み立て
    n = len(results)
    with_learning = sum(
        1
        for _, r in results
        if r["status"] == "done" and not r["note"].startswith("no_learnings")
    )
    errors = sum(1 for _, r in results if r["status"] == "error")
    oob_any = [p for _, r in results for p in r.get("out_of_bounds", [])]
    mode = "ドライラン" if config.LEARNING_REVIEW_DRYRUN else "本番"
    lines = [
        f"🧠 **今夜の学習ラン**（{mode}）: {n}件レビュー / {with_learning}件で学びあり "
        f"/ エラー{errors}件 / skipped(too_short){skipped}件"
    ]
    for sess, r in results:
        if r["status"] == "done" and not r["note"].startswith("no_learnings"):
            tag = "📝"
        elif r["status"] == "error":
            tag = "⚠️"
        else:
            tag = "—"
        lines.append(
            f"{tag} {sess.get('channel_name') or sess['channel_id']} "
            f"({sess['review_date']}): {r['note'][:200]}"
        )
    if oob_any:
        lines.append(f"🚨 範囲外への書き込みを検出し revert しました: {oob_any}")
    if _send_fn:
        try:
            await _send_fn(config.LEARNING_NOTIFY_CHANNEL, "\n".join(lines))
        except Exception:  # noqa: BLE001
            logger.exception("learning_review: notify failed")
    logger.info("learning_review done: %s", lines[0])


async def knowledge_digest():
    """夜間バッチ: その日のチャンネルごとの会話を構造化議事録にする（フェーズ1）。"""
    if not config.KNOWLEDGE_DIGEST_ENABLED:
        logger.info("knowledge_digest: disabled (KNOWLEDGE_DIGEST_ENABLED=false), skip")
        return
    logger.info("Running knowledge_digest...")
    import datetime as _dt

    from knowledge import digest as kdigest

    today = _dt.date.today().strftime("%Y-%m-%d")
    loop = asyncio.get_event_loop()
    run = await loop.run_in_executor(
        None,
        lambda: kdigest.build_daily_digests(
            date=today,
            learning_db=config.LEARNING_DB_PATH,
            knowledge_db=config.KNOWLEDGE_DB_PATH,
            view_dir=config.KNOWLEDGE_VIEW_DIR,
            company_dir=config.COMPANY_DIR,
            meetings_dir=config.COMPANY_DIR / "meetings",
            model=config.REVIEW_MODEL_CLI,
            min_turns=config.KNOWLEDGE_MIN_DIGEST_TURNS,
            notification_channel_ids=config.KNOWLEDGE_NOTIFICATION_CHANNEL_IDS,
            timeout_sec=config.KNOWLEDGE_DIGEST_TIMEOUT_SEC,
            max_sessions=config.KNOWLEDGE_DIGEST_MAX_SESSIONS,
        ),
    )
    lines = [
        f"📋 **今夜の議事録化**（{today}）: {run.processed}件 / 失敗{run.failed}件 "
        f"/ スキップ{run.skipped}件 / council索引{run.council_indexed}件"
    ]
    for note in run.notes:
        lines.append(f"⚠️ {note}")
    if _send_fn:
        try:
            await _send_fn(config.KNOWLEDGE_NOTIFY_CHANNEL, "\n".join(lines))
        except Exception:  # noqa: BLE001
            logger.exception("knowledge_digest: notify failed")
    logger.info("knowledge_digest done: %s", lines[0])


async def learning_curate():
    """週次キュレーター（weekly_review から呼ばれる、または !learning curate）。"""
    if not config.LEARNING_CURATOR_ENABLED:
        logger.info("learning_curate: disabled (LEARNING_CURATOR_ENABLED=false), skip")
        return
    logger.info(
        "Running learning_curate (dryrun=%s)...", config.LEARNING_CURATOR_DRYRUN
    )
    from learning import curator

    loop = asyncio.get_event_loop()
    run_fn = functools.partial(
        curator.run_curation,
        config.COMPANY_DIR,
        config.CURATOR_MODEL_CLI,
        config.SKILL_HITS_PATH,
        allowed_tools=config.LEARNING_ALLOWED_TOOLS,
        dryrun_allowed_tools=config.LEARNING_DRYRUN_ALLOWED_TOOLS,
        disallowed_tools=config.LEARNING_DISALLOWED_TOOLS,
        timeout_sec=config.LEARNING_CURATOR_TIMEOUT_SEC,
        dryrun=config.LEARNING_CURATOR_DRYRUN,
    )
    res = await loop.run_in_executor(None, run_fn)
    mode_label = "ドライラン" if res.get("dryrun") else "本番"
    if res["status"] == "done":
        msg = (
            f"🧹 **今週のスキル棚卸し（{mode_label}）**: {res['summary']}\n"
            f"（巻き戻し基準コミット: `{res['head_before'][:10]}` — やりすぎなら `git -C .company revert` 可）"
        )
    else:
        msg = (
            f"⚠️ スキル棚卸しに失敗（{mode_label}）: {res['note']}"
            f"（スナップショット `.company/skills/.snapshots/` から復元可）"
        )
    if res.get("out_of_bounds"):
        msg += f"\n🚨 範囲外書き込みを revert: {res['out_of_bounds']}"
    if _send_fn:
        try:
            await _send_fn(config.LEARNING_NOTIFY_CHANNEL, msg)
        except Exception:  # noqa: BLE001
            logger.exception("learning_curate: notify failed")
    logger.info("learning_curate done: %s", res.get("summary") or res.get("note"))


def learning_prune():
    """会話ログの保持期間プルーニング（weekly_review から同期呼び出し）。"""
    from learning import store

    try:
        deleted = store.prune(
            config.LEARNING_DB_PATH, retention_days=config.TURNS_RETENTION_DAYS
        )
        logger.info("learning_prune: deleted %d old turns", deleted)
    except Exception:  # noqa: BLE001
        logger.exception("learning_prune failed")


async def ticket_monthly_archive():
    """月初4:00 — done/ の古いチケットを archive/<YYYY-MM>/ に移動する。"""
    logger.info("Running monthly ticket archive...")
    try:
        from tools.tickets import archive_old_done

        moved = archive_old_done(days=30)
        if moved and _send_fn:
            await _send_fn(
                "秘書-steve-general",
                f"🗂️ チケットアーカイブ完了 — done/ から **{moved}件** を archive/ に移動しました。",
            )
        logger.info(f"Monthly ticket archive: moved={moved}")
    except Exception as e:
        logger.error(f"ticket_monthly_archive failed: {e}")
    logger.info("Weekly review sent")


# --- Email draft auto-creation (0/6/12/18時) ---

_NOISE_FROM_PATTERNS = (
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "notifications@",
    "notify@",
    "mailer-daemon",
    "info@aucfan",
    "@message.fedex.com",
    "@fedex.com",
    "alert@",
    "alerts@",
    "auto@",
    "automated@",
    "system@",
    "ebay@ebay.com",
    "@deals.aliexpress.com",
    "@email.aliexpress.com",
    "@notice.aliexpress.com",
    "info@fmclub.asia",
)

# AI が「返信不要」と判断したのに本文を書いてしまった場合の保険:
# 本文の冒頭にこれらのフレーズが含まれたら下書きを作らない
_NOISE_BODY_PHRASES = (
    "これは",  # 「これは～です」型のメタ説明
    "this is an automated",
    "this is a system",
    "返信は不要",
    "返信不要",
    "自動配信",
    "自動送信",
    "自動通知",
    "no-reply",
    "noreply",
)
_NOISE_SUBJECT_PATTERNS = (
    "メルマガ",
    "ニュースレター",
    "newsletter",
    "お得情報",
    "キャンペーン",
    "[広告]",
    "[PR]",
    "配信停止",
    "unsubscribe",
    "アラート",
    "自動配信",
    "自動送信",
    "自動通知",
    "alert",
    "no-reply",
    # b-manager 自身の eBay 在庫切れ通知（返信対象外）
    "【ebay在庫切れ】",
    "在庫切れ",
    # マーケ系・出品ピックアップ通知（商業的勧誘・返信不要）
    "イイですね",
    "いいですね",
    "🔥",
    "大特価",
    "限定セール",
    "セール中",
    "今だけ",
    "出品情報",
    "新着出品",
    "おすすめ商品",
    "再入荷",
    "値下げ",
    "クーポン",
    "ポイント",
)


def _is_noise_email(email: dict) -> bool:
    sender = (email.get("from") or "").lower()
    subject = (email.get("subject") or "").lower()
    if any(p in sender for p in _NOISE_FROM_PATTERNS):
        return True
    if any(p.lower() in subject for p in _NOISE_SUBJECT_PATTERNS):
        return True
    return False


def _extract_email_address(from_header: str) -> str:
    """'Name <user@example.com>' → 'user@example.com'. Falls back to original."""
    import re

    m = re.search(r"<([^>]+)>", from_header or "")
    if m:
        return m.group(1).strip()
    return (from_header or "").strip()


# メール下書きの日次カウンタ（朝のbriefingで集計→リセット）
# Claude Max のサブスク枠で動かしているため使用量はAPIコンソールから見えない。
# 自前でカウンタを持って「何件試行/成功/失敗したか」を可視化する。
_email_draft_stats = {
    "attempted": 0,  # claude -p を呼んだ回数
    "succeeded": 0,  # 下書きまで作成成功
    "failed_rate_limit": 0,  # Claude Max のレート制限
    "failed_other": 0,  # その他の失敗（タイムアウト/プロセスエラー）
    "skipped_filter": 0,  # subject/from のノイズ事前除外
    "skipped_dup": 0,  # 既に下書きあり
    "skipped_ai": 0,  # AIが [SKIP] 返答
    "skipped_phrase": 0,  # AIメタコメント検知
}


def _reset_email_draft_stats() -> dict:
    """カウンタをスナップショット返却して0にリセット。morning_briefing から呼ぶ。"""
    snapshot = dict(_email_draft_stats)
    for k in _email_draft_stats:
        _email_draft_stats[k] = 0
    return snapshot


# Claude Max のレート制限を検知するためのフレーズ（claude -p の出力に含まれる）
_RATE_LIMIT_MARKERS = (
    "hit your limit",
    "rate limit",
    "resets 7am",
    "usage limit",
)


def _generate_draft_via_cli(email: dict) -> Optional[str]:
    """Generate a reply draft body via `claude -p` (Claude Max subscription).

    Returns:
        - 下書き本文（str）on success
        - None on failure（呼び出し側でログのみ、Steve通知は抑制）

    レート制限を検知した場合は logger.info（warningではない）で静かに記録し、
    カウンタに `failed_rate_limit` として集計する。

    Security note: --dangerously-skip-permissions は非対話サブプロセス実行に必須
    （無いと IDE handshake → UND_ERR_INVALID_ARG で失敗）。--disallowedTools で
    実行系/ネットワーク系/書き込み系を全て封じてプロンプトインジェクション耐性を確保。
    """
    import subprocess

    _email_draft_stats["attempted"] += 1

    prompt = (
        "以下のメールへの返信下書きを作成してください。\n\n"
        "## 重要ルール（厳守）\n"
        "1. 自動配信・通知系・メルマガ・アラート・返信不要のメールと判断したら、"
        "本文に何も書かず `[SKIP]` の5文字だけを返してください\n"
        "2. 出力は「メール本文そのもの」のみ。前置き・補足・解説・メタコメントは一切禁止\n"
        "   - NG例: 「これは～です」「ご希望であれば～」「以下の下書きをどうぞ」\n"
        "   - NG例: 末尾の補足ブロック（**補足:**、---、など）\n"
        "3. 日本語メールなら日本語で、英語メールなら英語で返信\n"
        "4. 署名は「大塚」程度に簡潔に\n"
        "5. 不明な点は確認のお願いとして書く（憶測で約束しない）\n\n"
        "## 入力\n"
        f"From: {email.get('from')}\n"
        f"Subject: {email.get('subject')}\n"
        f"Snippet: {email.get('snippet')}\n"
    )
    try:
        cmd = [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "text",
            "--max-turns",
            "1",
            "--dangerously-skip-permissions",
            "--disallowedTools",
            "Bash WebFetch WebSearch Task Edit Write",
        ]
        if config.CLAUDE_MODEL_CLI:
            cmd.extend(["--model", config.CLAUDE_MODEL_CLI])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(config.COMPANY_DIR),
        )

        combined = (result.stdout or "") + " " + (result.stderr or "")
        is_rate_limit = any(m in combined.lower() for m in _RATE_LIMIT_MARKERS)

        if result.returncode != 0:
            if is_rate_limit:
                _email_draft_stats["failed_rate_limit"] += 1
                logger.info("claude -p hit Claude Max rate limit (silently skipped)")
            else:
                _email_draft_stats["failed_other"] += 1
                logger.warning(
                    f"claude -p draft generation failed rc={result.returncode} "
                    f"stderr={result.stderr[:300]} stdout={result.stdout[:300]}"
                )
            return None

        body = (result.stdout or "").strip()
        if not body:
            if is_rate_limit:
                _email_draft_stats["failed_rate_limit"] += 1
                logger.info(
                    "claude -p returned empty (likely rate limit, silently skipped)"
                )
            else:
                _email_draft_stats["failed_other"] += 1
                logger.warning("claude -p returned empty body")
            return None

        # 成功扱いは呼び出し側で confirm（[SKIP] 判定後）
        return body
    except Exception as e:
        _email_draft_stats["failed_other"] += 1
        logger.error(f"_generate_draft_via_cli failed: {e}")
        return None


async def hourly_email_drafts():
    """30分ごと(7-23時) — 未読メールに対して返信下書きを自動作成。

    - 重複除外: 既に下書きがあるスレッドはスキップ
    - ノイズ除外: noreply / メルマガ系 / AIが返信不要と判断したもの
    - 通知: **成功時のみ** ceo-steve-general へサマリー送信。失敗（レート制限/
      生成失敗）はカウンタに集計し、毎朝の morning_briefing で日次レポートとして
      まとめて送る（30分ごとのノイズ通知を抑制）。
    """
    logger.info("Running hourly email drafts...")
    try:
        from tools import gmail_tool

        loop = asyncio.get_event_loop()

        emails = await loop.run_in_executor(
            None, lambda: gmail_tool.get_unread_emails(max_results=30)
        )
        drafted = await loop.run_in_executor(
            None, lambda: gmail_tool.get_existing_draft_thread_ids(max_results=200)
        )

        new_drafts = []
        create_draft_failures = []  # create_draft 自体の失敗（Gmail API側）— これは通知する

        for e in emails:
            tid = e.get("threadId")
            subj = (e.get("subject") or "")[:60]
            if tid in drafted:
                _email_draft_stats["skipped_dup"] += 1
                continue
            if _is_noise_email(e):
                _email_draft_stats["skipped_filter"] += 1
                continue

            # claude -p 失敗はここで return None。カウンタは _generate_draft_via_cli 内で更新済み。
            body = await loop.run_in_executor(None, _generate_draft_via_cli, e)
            if not body:
                continue
            if "[SKIP]" in body[:20].upper():
                _email_draft_stats["skipped_ai"] += 1
                continue
            # AI が指示を無視して「これは～自動配信」と前置きを書いた場合の保険
            body_head = body[:80].lower()
            if any(p.lower() in body_head for p in _NOISE_BODY_PHRASES):
                logger.info(
                    f"AI returned meta-comment instead of [SKIP] — treating as noise: {subj}"
                )
                _email_draft_stats["skipped_phrase"] += 1
                continue

            try:
                to_addr = _extract_email_address(e.get("from", ""))
                subject = e.get("subject") or "(無題)"
                if not subject.lower().startswith("re:"):
                    subject = f"Re: {subject}"
                await loop.run_in_executor(
                    None,
                    lambda body=body, to_addr=to_addr, subject=subject, tid=tid, e=e: (
                        gmail_tool.create_draft(
                            to=to_addr,
                            subject=subject,
                            body=body,
                            thread_id=tid,
                            in_reply_to=e.get("messageId") or None,
                        )
                    ),
                )
                new_drafts.append(e)
                _email_draft_stats["succeeded"] += 1
                if tid:
                    drafted.add(tid)  # 同一実行内の重複防止
            except Exception as ce:
                logger.error(f"create_draft failed for {e.get('id')}: {ce}")
                create_draft_failures.append(
                    (subj, f"create_draft 失敗: {str(ce)[:80]}")
                )

        logger.info(
            "hourly_email_drafts: new=%d create_draft_fail=%d (counters: %s)",
            len(new_drafts),
            len(create_draft_failures),
            _email_draft_stats,
        )

        # 通知は「成功あり」または「Gmail API側の失敗あり」のときのみ。
        # claude -p の失敗（レート制限/生成失敗）は日次サマリに集約。
        if (new_drafts or create_draft_failures) and _send_fn:
            lines = []
            if new_drafts:
                lines.append(
                    f"📧 メール返信下書き **{len(new_drafts)}件** 作成しました"
                )
                for e in new_drafts[:10]:
                    sender_short = (e.get("from") or "")[:40]
                    subj_short = (e.get("subject") or "")[:50]
                    lines.append(f"- `{sender_short}` — {subj_short}")
                if len(new_drafts) > 10:
                    lines.append(f"…他 {len(new_drafts) - 10}件")
            if create_draft_failures:
                if lines:
                    lines.append("")
                lines.append(
                    f"⚠️ Gmail下書き作成に失敗 **{len(create_draft_failures)}件**（手動対応してください）"
                )
                for subj, reason in create_draft_failures[:10]:
                    lines.append(f"- {subj} — {reason}")
                if len(create_draft_failures) > 10:
                    lines.append(f"…他 {len(create_draft_failures) - 10}件")
            if new_drafts:
                lines.append("\nGmail下書きから確認・編集して送信してください。")
            await _send_fn("ceo-steve-general", "\n".join(lines))
    except Exception as e:
        logger.error(f"hourly_email_drafts failed: {e}", exc_info=True)


def _format_email_draft_daily_report(stats: dict) -> Optional[str]:
    """日次集計を読みやすいテキストに整形。全件0なら None。"""
    if not any(stats.values()):
        return None
    total_attempts = stats.get("attempted", 0)
    succeeded = stats.get("succeeded", 0)
    rate_limit = stats.get("failed_rate_limit", 0)
    other = stats.get("failed_other", 0)
    ai_skip = stats.get("skipped_ai", 0)
    phrase = stats.get("skipped_phrase", 0)
    noise = stats.get("skipped_filter", 0)
    dup = stats.get("skipped_dup", 0)

    lines = [
        "📊 **昨日のメール下書き集計**",
        f"- claude呼び出し: {total_attempts}回 / 下書き作成成功: {succeeded}件",
    ]
    if rate_limit or other:
        fail_parts = []
        if rate_limit:
            fail_parts.append(f"Max枠制限 {rate_limit}件")
        if other:
            fail_parts.append(f"その他 {other}件")
        lines.append(f"- 生成失敗: " + " / ".join(fail_parts))
    if ai_skip or phrase:
        lines.append(f"- AI判定 [SKIP]: {ai_skip + phrase}件")
    if noise or dup:
        lines.append(f"- 事前除外: ノイズ {noise}件 / 重複 {dup}件")
    return "\n".join(lines)


_JOB_ERROR_NOTIFY = {
    "learning_review": config.LEARNING_NOTIFY_CHANNEL,
    "weekly_review": config.LEARNING_NOTIFY_CHANNEL,
    "knowledge_digest": config.KNOWLEDGE_NOTIFY_CHANNEL,
}


def _on_job_error(event):
    """APScheduler ジョブが例外を投げたらログ + 一部ジョブは Discord にも通知（best-effort）。"""
    logger.error("Scheduler job %s raised: %s", event.job_id, event.exception)
    notify_channel = _JOB_ERROR_NOTIFY.get(event.job_id)
    if notify_channel and _send_fn:
        try:
            # AsyncIOScheduler のリスナーはイベントループ内で呼ばれる前提（get_running_loop）。
            asyncio.get_running_loop().create_task(
                _send_fn(
                    notify_channel,
                    f"⚠️ スケジューラジョブ `{event.job_id}` が例外: {event.exception}",
                )
            )
        except RuntimeError:
            pass
        except Exception:  # noqa: BLE001
            pass


def setup_scheduler(send_fn, task_view_fn=None):
    """Setup APScheduler with scheduled jobs. Safe to call multiple times (e.g. on Discord reconnect)."""
    global _scheduler, _scheduler_started, _send_fn, _task_view_fn
    _send_fn = send_fn
    _task_view_fn = task_view_fn

    # Prevent duplicate schedulers on reconnect (flag-based to avoid race condition)
    if _scheduler_started:
        logger.info("Scheduler already running — skipping re-init")
        return
    _scheduler_started = True

    _scheduler = AsyncIOScheduler(
        timezone="Asia/Tokyo", job_defaults={"misfire_grace_time": 300}
    )
    _scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)

    _scheduler.add_job(
        fetch_ai_news_cache,
        "cron",
        hour=7,
        minute=0,
        name="AIニュースキャッシュ取得",
    )
    _scheduler.add_job(
        morning_briefing,
        "cron",
        hour=config.MORNING_BRIEFING_HOUR,
        minute=config.MORNING_BRIEFING_MINUTE,
        name="朝のブリーフィング",
    )
    _scheduler.add_job(
        evening_review,
        "cron",
        hour=config.EVENING_REVIEW_HOUR,
        minute=config.EVENING_REVIEW_MINUTE,
        name="夕方の振り返り",
    )
    _scheduler.add_job(
        ad_report_analysis,
        "cron",
        hour=8,
        minute=5,
        name="広告レポート分析",
    )
    _scheduler.add_job(
        dream_checkin,
        "cron",
        day_of_week="wed",
        hour=21,
        minute=0,
        name="夢チェックイン",
    )
    _scheduler.add_job(
        strategic_proposal,
        "cron",
        day_of_week="sun",
        hour=19,
        minute=0,
        id="strategic_proposal",
        name="週次戦略提案（Reid）",
    )
    _scheduler.add_job(
        weekly_review,
        "cron",
        day_of_week="sun",
        hour=21,
        minute=0,
        id="weekly_review",
        name="週次レビュー",
    )
    # Phase 5: 朝の情報収集（Xバズ・ニュースレター・AIトレンド）
    _scheduler.add_job(
        news_collection,
        "cron",
        hour=7,
        minute=0,
        name="情報収集（X/ニュースレター）",
    )
    # Phase 3: 翌日のミーティング事前リサーチ
    _scheduler.add_job(
        pre_meeting_research,
        "cron",
        hour=20,
        minute=30,
        name="翌日ミーティング事前リサーチ",
    )
    # Phase 6: 月初にチケットの古いdoneをarchiveに移動
    _scheduler.add_job(
        ticket_monthly_archive,
        "cron",
        day=1,
        hour=4,
        minute=0,
        name="チケット月次アーカイブ",
    )
    # メール返信下書き自動作成（30分ごと・7-23時）— サイレント実行、新規分+失敗分を通知
    _scheduler.add_job(
        hourly_email_drafts,
        "cron",
        hour="7-23",
        minute="0,30",
        name="メール返信下書き自動作成",
    )
    # Tier 3-A: 深夜2:00 主要プロダクトサイト疎通チェック（失敗のみJackに通知）
    _scheduler.add_job(
        nightly_site_check,
        "cron",
        hour=2,
        minute=0,
        name="夜間サイト疎通チェック",
    )
    # Tier 3-D: 深夜2:30 VPS ヘルスチェック（report-only結果を集約・エラー時のみJackに通知）
    _scheduler.add_job(
        nightly_vps_health_check,
        "cron",
        hour=2,
        minute=30,
        name="夜間VPSヘルスチェック",
    )
    # Tier 3-B: 深夜3:00 直近24h commit を code-reviewer 風レビュー（重大指摘のみLarryに通知）
    _scheduler.add_job(
        nightly_commit_review,
        "cron",
        hour=3,
        minute=0,
        name="夜間コミットレビュー",
    )
    # Tier 3-E: 深夜4:00 launchd 生存確認（沈黙ジョブをJackに通知）
    _scheduler.add_job(
        nightly_launchd_liveness_check,
        "cron",
        hour=4,
        minute=0,
        name="夜間launchd生存確認",
    )
    # Tier 3-F: 深夜5:00 APIトークン期限・生存確認（残14日以下/エラーをLarryに通知）
    _scheduler.add_job(
        nightly_token_expiry_check,
        "cron",
        hour=5,
        minute=0,
        name="夜間APIトークン期限確認",
    )
    # Tier 3-G: 深夜5:30 Discord Webhook 死活確認（404/401をJackに通知）
    _scheduler.add_job(
        nightly_discord_webhook_check,
        "cron",
        hour=5,
        minute=30,
        name="夜間Discord Webhook死活",
    )
    # Tier 3-H: 深夜5:45 VPS DB バックアップ整合性確認（古い/欠落をJackに通知）
    _scheduler.add_job(
        nightly_backup_integrity_check,
        "cron",
        hour=5,
        minute=45,
        name="夜間DBバックアップ整合性",
    )
    # Tier 3-I: 深夜6:00 SNS 0 投稿アラート (saimu-media Threads)
    _scheduler.add_job(
        nightly_sns_posting_check,
        "cron",
        hour=6,
        minute=0,
        name="夜間SNS投稿0件アラート",
    )
    # Tier 3-J: 10分毎 d-manager 死亡検知ハートビート (VPS に SSH+touch)
    _scheduler.add_job(
        d_manager_heartbeat,
        "cron",
        minute="*/10",
        name="d-manager死活ハートビート",
    )
    # 学習ループ: 夜間23:00 にセッションレビュー
    _scheduler.add_job(
        learning_review,
        "cron",
        hour=config.LEARNING_REVIEW_HOUR,
        minute=0,
        id="learning_review",
        name="学習ループ夜間レビュー",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        knowledge_digest,
        "cron",
        hour=config.KNOWLEDGE_DIGEST_HOUR,
        minute=config.KNOWLEDGE_DIGEST_MINUTE,
        id="knowledge_digest",
        name="知見エンジン: 夜間議事録化",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )

    _scheduler.start()
    logger.info(f"Scheduler started with {len(_scheduler.get_jobs())} jobs")
