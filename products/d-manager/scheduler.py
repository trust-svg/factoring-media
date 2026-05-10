"""Scheduled tasks — morning briefing, evening review, task board, KPI reports."""

import logging
import asyncio
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
from ai_engine import process_message
from tools.dream import get_dream_briefing, get_pyramid_summary, list_dreams
from tools.divination import get_daily_summary, get_monthly_summary

logger = logging.getLogger(__name__)
_scheduler: Optional[AsyncIOScheduler] = None
_scheduler_started = False  # True once start() has been called
_send_fn = None  # send_to_channel(channel_name, text, view=None)
_task_view_fn = None  # function to create TaskBoardView(tasks)

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
        await _send_fn("運営-jack-operations", "\n".join(lines))

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
            log_result = subprocess.run(
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
            diff_result = subprocess.run(
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
            result = subprocess.run(
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
        await _send_fn(
            "運営-jack-operations",
            f"🚨 **VPS ヘルスチェック異常**\n\n```\n{output[:1500]}\n```",
        )

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


async def nightly_launchd_liveness_check():
    """Tier 3-E: 深夜4:00 — launchd 各ジョブの生存確認（ログ mtime ベース）。

    ジョブのログが期待される間隔より古ければ「沈黙」と判定し、Jack に通知。
    """
    import plistlib

    logger.info("Running nightly_launchd_liveness_check...")
    today_iso = date.today().isoformat()

    plists = sorted(LAUNCHD_PLIST_DIR.glob(LAUNCHD_PLIST_PATTERN))
    now_ts = datetime.now().timestamp()

    silent: list[tuple[str, str, int]] = []  # (label, last_mtime_str, age_hours)
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
        else:
            healthy_count += 1

    summary_block = (
        f"\n## launchd 生存確認 (深夜4:00)\n\n"
        f"healthy: {healthy_count}件 / silent: {len(silent)}件 / skipped: {len(skipped)}件\n\n"
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

    if silent and _send_fn:
        lines = [f"🚨 **launchd 沈黙ジョブ検出 ({len(silent)}件)**\n"]
        for label, last, age_h in silent:
            if age_h < 0:
                lines.append(f"- **{label}**: ログなし")
            else:
                lines.append(f"- **{label}**: 最終 {last} ({age_h}h前)")
        await _send_fn("運営-jack-operations", "\n".join(lines))

    logger.info(
        f"nightly_launchd_liveness_check: healthy={healthy_count} silent={len(silent)} skipped={len(skipped)}"
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
        await _send_fn("開発-larry-product", "\n".join(lines))

    logger.info(
        f"nightly_token_expiry_check: {len(results)} checked, {len(serious)} alerts"
    )


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


async def morning_briefing():
    """Generate and send morning briefing + task board."""
    logger.info("Running morning briefing...")

    # 0. Tier 3-C: 夜間QA サマリを先頭に表示（あれば）
    nightly_summary = _read_nightly_qa_summary()
    if nightly_summary and _send_fn:
        await _send_fn("ceo-steve-general", nightly_summary)
        logger.info("Nightly QA summary sent")

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
        f"## 今日の教え\n{teaching}\n\n"
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
    """朝7:00 — Xのバズ投稿とニュースレターを収集・要約してキャッシュする。

    結果は `.company/secretary/news_cache/YYYY-MM-DD.md` に保存し、
    morning_briefing がプロンプトで参照する。
    """
    logger.info("Running news collection...")
    cache_dir = config.COMPANY_DIR / "secretary" / "news_cache"
    today_iso = date.today().isoformat()
    cache_path = cache_dir / f"{today_iso}.md"

    prompt = (
        f"今朝の情報収集をお願いします。結果を1ファイルにまとめて保存してください。\n\n"
        "## 収集対象\n"
        "1. **X（Twitter）バズ投稿**: tools/x_scraper.py を使用し、AI/起業/eBay/マーケ系で過去24時間に1万RT以上の投稿を5件抽出\n"
        "2. **ニュースレター要約**: Gmailで Newsletter / List-Unsubscribe ヘッダ付きまたは「ニュースレター」「メルマガ」ラベルのメールから、過去24時間の重要トピックを5件抽出\n"
        "3. **AIトレンド**: Web検索で『AI トレンド YYYY-MM』の最新情報3件\n\n"
        "## 出力先\n"
        f"{cache_path} に以下のフォーマットで保存:\n"
        "---\ndate: YYYY-MM-DD\n---\n\n"
        "## 🐦 X バズ投稿\n（5件・URL付き）\n\n"
        "## 📧 ニュースレター要約\n（5件・差出人と件名）\n\n"
        "## 🤖 AIトレンド\n（3件・URL付き）\n\n"
        "## ルール\n"
        "- 取得失敗があれば該当セクションに「取得失敗」と明示\n"
        "- 推測で埋めない・社訓1遵守\n"
        "- Discordには件数のみ要約（3行以内）で報告"
    )
    loop = asyncio.get_event_loop()
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


def _generate_draft_via_cli(email: dict) -> Optional[str]:
    """Generate a reply draft body via `claude -p` (subscription, no API cost)."""
    import subprocess

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
        result = subprocess.run(
            [
                "claude",
                "-p",
                prompt,
                "--output-format",
                "text",
                "--max-turns",
                "3",
                "--dangerously-skip-permissions",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(config.COMPANY_DIR),
        )
        if result.returncode != 0:
            logger.warning(
                f"claude -p draft generation failed rc={result.returncode} stderr={result.stderr[:300]}"
            )
            return None
        body = (result.stdout or "").strip()
        return body or None
    except Exception as e:
        logger.error(f"_generate_draft_via_cli failed: {e}")
        return None


async def hourly_email_drafts():
    """0/6/12/18時 — 未読メールに対して返信下書きを自動作成。

    - 重複除外: 既に下書きがあるスレッドはスキップ
    - ノイズ除外: noreply / メルマガ系は除外
    - 通知: 新規分があれば ceo-steve-general へサマリー送信
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
        skipped_dup = 0
        skipped_noise = 0
        failed = 0

        for e in emails:
            tid = e.get("threadId")
            if tid in drafted:
                skipped_dup += 1
                continue
            if _is_noise_email(e):
                skipped_noise += 1
                continue

            body = await loop.run_in_executor(None, _generate_draft_via_cli, e)
            if not body:
                failed += 1
                continue
            if "[SKIP]" in body[:20].upper():
                skipped_noise += 1
                continue
            # AI が指示を無視して「これは～自動配信」と前置きを書いた場合の保険
            body_head = body[:80].lower()
            if any(p.lower() in body_head for p in _NOISE_BODY_PHRASES):
                logger.info(
                    f"AI returned meta-comment instead of [SKIP] — treating as noise: {e.get('subject', '')[:40]}"
                )
                skipped_noise += 1
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
                if tid:
                    drafted.add(tid)  # 同一実行内の重複防止
            except Exception as ce:
                logger.error(f"create_draft failed for {e.get('id')}: {ce}")
                failed += 1

        logger.info(
            f"hourly_email_drafts: new={len(new_drafts)} dup={skipped_dup} noise={skipped_noise} failed={failed}"
        )

        if new_drafts and _send_fn:
            lines = [f"📧 メール返信下書き **{len(new_drafts)}件** 作成しました"]
            for e in new_drafts[:10]:
                sender_short = (e.get("from") or "")[:40]
                subj_short = (e.get("subject") or "")[:50]
                lines.append(f"- `{sender_short}` — {subj_short}")
            if len(new_drafts) > 10:
                lines.append(f"…他 {len(new_drafts) - 10}件")
            lines.append("\nGmail下書きから確認・編集して送信してください。")
            await _send_fn("ceo-steve-general", "\n".join(lines))
    except Exception as e:
        logger.error(f"hourly_email_drafts failed: {e}", exc_info=True)


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
        weekly_review,
        "cron",
        day_of_week="sun",
        hour=21,
        minute=0,
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
    # メール返信下書き自動作成（0/6/12/18時）— サイレント実行、新規分のみ通知
    _scheduler.add_job(
        hourly_email_drafts,
        "cron",
        hour="0,6,12,18",
        minute=0,
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

    _scheduler.start()
    logger.info(f"Scheduler started with {len(_scheduler.get_jobs())} jobs")
