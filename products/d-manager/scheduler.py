"""Scheduled tasks — morning briefing, evening review, task board, KPI reports."""

import logging
import asyncio
import json
import re
import urllib.request
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
from ai_engine import process_message
from tools.dream import get_dream_briefing, get_pyramid_summary, list_dreams

logger = logging.getLogger(__name__)
_scheduler: Optional[AsyncIOScheduler] = None
_send_fn = None

JST = timezone(timedelta(hours=9))
ACTIVE_TASKS_PATH = config.COMPANY_DIR / "secretary" / "todos" / "active.md"

# Department -> channel mapping for task routing
DEPT_CHANNELS = {
    "アイ": "秘書-アイ-general",
    "リク": "運営-リク-operations",
    "レン": "開発-レン-product",
    "ユウ": "マーケティング-ユウ-marketing",
    "ケイ": "経理-ケイ-finance",
    "アキラ": "調査-アキラ-research",
    "ナオ": "戦略-ナオ-strategy",
}


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
    """Parse active.md and return list of task dicts."""
    if not ACTIVE_TASKS_PATH.exists():
        return []

    content = ACTIVE_TASKS_PATH.read_text(encoding="utf-8")
    tasks = []
    # Match: - [ ] Task name | 担当: X | 期限: Y | 追加: Z | スキップ: N
    pattern = re.compile(
        r"^- \[ \] (.+?) \| 担当: (\S+) \| 期限: (\S+) \| 追加: (\S+) \| スキップ: (\d+)",
        re.MULTILINE,
    )
    for m in pattern.finditer(content):
        added = m.group(4)
        days = (date.today() - date.fromisoformat(added)).days
        tasks.append({
            "name": m.group(1),
            "owner": m.group(2),
            "deadline": m.group(3),
            "added": added,
            "skip_count": int(m.group(5)),
            "age_days": days,
        })
    return tasks


def _build_task_board() -> str:
    """Build a formatted task board message for Discord."""
    tasks = _parse_active_tasks()
    today = date.today().isoformat()

    if not tasks:
        return f"📋 **タスクボード — {today}**\n\nタスクなし！素晴らしい！🎉"

    lines = [f"📋 **タスクボード — {today}**\n"]

    # Categorize
    urgent = [t for t in tasks if t["deadline"] != "なし" and t["deadline"] <= today]
    overdue = [t for t in tasks if t["age_days"] >= 7 and t not in urgent]
    warning = [t for t in tasks if 3 <= t["age_days"] < 7 and t not in urgent]
    normal = [t for t in tasks if t["age_days"] < 3 and t not in urgent]
    stale = [t for t in tasks if t["skip_count"] >= 3]

    if urgent:
        lines.append("🚨 **期限切れ・緊急**")
        for t in urgent:
            lines.append(f"  ⚡ **{t['name']}** → {t['owner']}（期限: {t['deadline']}）")
        lines.append("")

    if stale:
        lines.append("⚠️ **3回スキップ — やる？捨てる？**")
        for t in stale:
            lines.append(f"  🗑️ **{t['name']}** → {t['owner']}（{t['age_days']}日経過）")
        lines.append("")

    if overdue:
        lines.append("🟠 **7日以上放置**")
        for t in overdue:
            lines.append(f"  📌 {t['name']} → {t['owner']}（{t['age_days']}日）")
        lines.append("")

    if warning:
        lines.append("🟡 **3日以上**")
        for t in warning:
            lines.append(f"  📌 {t['name']} → {t['owner']}（{t['age_days']}日）")
        lines.append("")

    if normal:
        lines.append("🟢 **新規・通常**")
        for t in normal:
            lines.append(f"  ✏️ {t['name']} → {t['owner']}")
        lines.append("")

    lines.append(f"合計: **{len(tasks)}件** | 放置警告: {len(overdue)}件 | 要判断: {len(stale)}件")
    return "\n".join(lines)


def _increment_skip_counts():
    """Increment skip count for all incomplete tasks (called at evening review)."""
    if not ACTIVE_TASKS_PATH.exists():
        return

    content = ACTIVE_TASKS_PATH.read_text(encoding="utf-8")
    pattern = re.compile(r"(- \[ \] .+?\| スキップ: )(\d+)")

    def increment(m):
        return f"{m.group(1)}{int(m.group(2)) + 1}"

    updated = pattern.sub(increment, content)

    # Update the 'updated' date in frontmatter
    updated = re.sub(
        r'updated: "\d{4}-\d{2}-\d{2}"',
        f'updated: "{date.today().isoformat()}"',
        updated,
    )
    ACTIVE_TASKS_PATH.write_text(updated, encoding="utf-8")
    logger.info("Skip counts incremented for all active tasks")


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

    # eBay KPI → リク（運営）
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

    # Threads KPI → ユウ（マーケティング）
    if config.THREADS_AUTO_URL:
        base = config.THREADS_AUTO_URL.rstrip("/")
        status = _api_get(f"{base}/api/status")
        if status:
            kpi["marketing"] = f"Threads状況: {json.dumps(status, ensure_ascii=False)}"

    return kpi


# --- Department morning reports ---

DEPT_REPORT_PROMPTS = {
    "operations": (
        "リク",
        "運営-リク-operations",
        "おはようございます。eBay運営の朝レポートをお願いします。"
        "以下のKPIデータを元に、売上状況・在庫アラート・今日の優先アクションを報告してください。"
        "短く要点のみ（5行以内）で。\n\n{kpi_data}",
    ),
    "marketing": (
        "ユウ",
        "マーケティング-ユウ-marketing",
        "おはようございます。マーケティングの朝レポートをお願いします。"
        "以下のデータを元に、Threads運用状況・エンゲージメント・今日のアクションを報告してください。"
        "短く要点のみ（5行以内）で。\n\n{kpi_data}",
    ),
}


async def morning_briefing():
    """Generate and send morning briefing + task board."""
    logger.info("Running morning briefing...")

    # 1. Task board to 秘書チャンネル
    task_board = _build_task_board()
    if _send_fn:
        await _send_fn("秘書-アイ-general", task_board)
    logger.info("Task board sent")

    # 2. Send tasks to each department channel
    tasks = _parse_active_tasks()
    dept_tasks = {}
    for t in tasks:
        owner = t["owner"]
        dept_tasks.setdefault(owner, []).append(t)

    for owner, task_list in dept_tasks.items():
        channel = DEPT_CHANNELS.get(owner)
        if channel and channel != "秘書-アイ-general":
            lines = [f"📋 **{owner}の今日のタスク**\n"]
            for t in task_list:
                age = f"（{t['age_days']}日経過）" if t['age_days'] >= 3 else ""
                deadline = f" 🔥期限: {t['deadline']}" if t['deadline'] != "なし" else ""
                lines.append(f"- [ ] {t['name']}{deadline}{age}")
            lines.append("\n今日やる？延期？捨てる？")
            if _send_fn:
                await _send_fn(channel, "\n".join(lines))

    # 3. Dream briefing to 秘書チャンネル
    dream_summary = get_dream_briefing()
    if dream_summary and _send_fn:
        await _send_fn("秘書-アイ-general", dream_summary)
    logger.info("Dream briefing sent")

    # 4. AI briefing (アイ)
    teaching = _pick_daily_teaching()
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        process_message,
        f"おはようございます。朝のブリーフィングをお願いします。"
        f"カレンダー予定、未読メール、TODO（昨日の持ち越し含む）を確認して報告してください。"
        f"空き時間があれば活用提案もお願いします。"
        f"\n\n今日の教え: {teaching}",
        "secretary",
        "scheduler-briefing",
    )
    if _send_fn:
        await _send_fn("秘書-アイ-general", result)
    logger.info("Morning briefing sent")

    # 5. Department KPI reports (部門別朝レポート)
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
    """Generate and send evening review + increment skip counts."""
    logger.info("Running evening review...")

    # Increment skip counts for tasks not completed today
    _increment_skip_counts()

    # Build evening summary
    tasks = _parse_active_tasks()
    stale = [t for t in tasks if t["skip_count"] >= 3]

    if stale:
        lines = ["⚠️ **3回以上スキップされたタスク — 判断してください**\n"]
        for t in stale:
            lines.append(f"🗑️ **{t['name']}** → {t['owner']}（{t['age_days']}日経過、{t['skip_count']}回スキップ）")
            lines.append(f"  → 「やる」「捨てる」「来週に延期」のどれかを返信してください\n")
        if _send_fn:
            await _send_fn("秘書-アイ-general", "\n".join(lines))

    # AI review
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        process_message,
        "今日の振り返りをお願いします。TODOの完了率、未完了の持ち越し提案、明日の予定を確認してください。",
        "secretary",
        "scheduler-review",
    )
    if _send_fn:
        await _send_fn("秘書-アイ-general", result)
    logger.info("Evening review sent")


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
        await _send_fn("秘書-アイ-general", result)
    logger.info("Dream check-in sent")


async def ad_report_analysis():
    """Read ad report logs and have ユウ provide strategic analysis."""
    logger.info("Running ad report analysis...")

    meta_log = Path("/root/marketing/meta-ads/exports/cron.log")
    google_log = Path("/root/marketing/google-ads/cron.log")

    reports = []

    for name, log_path in [("Meta Ads", meta_log), ("Google Ads", google_log)]:
        if not log_path.exists():
            continue
        content = log_path.read_text(encoding="utf-8")
        # Get today's report (last run block)
        blocks = content.split("日次レポート生成")
        if len(blocks) >= 2:
            latest = blocks[-1]
            # Only use if it's from today
            today = date.today().isoformat()
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            if today in latest or yesterday in latest:
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
        await _send_fn("マーケティング-ユウ-marketing", result)
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
        await _send_fn("戦略-ナオ-strategy", result)
    logger.info("Weekly review sent")


def setup_scheduler(send_fn):
    """Setup APScheduler with scheduled jobs."""
    global _scheduler, _send_fn
    _send_fn = send_fn

    _scheduler = AsyncIOScheduler(timezone="Asia/Tokyo")

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
        minute=30,
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

    _scheduler.start()
    logger.info(f"Scheduler started with {len(_scheduler.get_jobs())} jobs")
