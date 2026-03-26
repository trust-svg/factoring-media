"""Dream / Goal management tool — dreams.md file backend.

Implements:
- Dream list (add / update / complete / list)
- Life Pyramid (7 categories, 3 levels)
- Future Timeline (age-based dream mapping)

Storage: ~/.company/secretary/dreams/dreams.md
"""

import re
import json
import logging
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)

DREAMS_DIR = config.COMPANY_DIR / "secretary" / "dreams"
DREAMS_PATH = DREAMS_DIR / "dreams.md"
JST = timezone(timedelta(hours=9))

# User profile for age calculation
BIRTH_YEAR = 1981

# Life Pyramid categories (7 fields, 3 levels)
PYRAMID_CATEGORIES = {
    # 基礎レベル (Foundation)
    "教養・知識": {"level": "基礎レベル", "emoji": "🎓"},
    "経済・モノ・お金": {"level": "基礎レベル", "emoji": "💰"},
    "心・精神": {"level": "基礎レベル", "emoji": "💚"},
    # 実現レベル (Realization)
    "プライベート・家族": {"level": "実現レベル", "emoji": "👨‍👩‍👧‍👦"},
    "社会・仕事": {"level": "実現レベル", "emoji": "💼"},
    # 結果レベル (Results)
    "健康・美・知恵": {"level": "結果レベル", "emoji": "✨"},
    # 未分類
    "未分類": {"level": "未分類", "emoji": "📌"},
}

# Dream entry pattern in MD
DREAM_PATTERN = re.compile(
    r"^- \[( |x)\] (.+?) \| カテゴリ: (.+?) \| 優先度: ([A-C]) "
    r"\| 進捗: (\d+)% \| 実現予定: (\S+) \| 登録: (\S+)"
    r"(?:\n  目標: (.+?))?$",
    re.MULTILINE,
)


def _ensure_dir():
    DREAMS_DIR.mkdir(parents=True, exist_ok=True)


def _read_dreams() -> str:
    _ensure_dir()
    if DREAMS_PATH.exists():
        return DREAMS_PATH.read_text(encoding="utf-8")
    return ""


def _write_dreams(content: str):
    _ensure_dir()
    DREAMS_PATH.write_text(content, encoding="utf-8")


def _init_dreams_file() -> str:
    """Create initial dreams.md if empty."""
    today = date.today().isoformat()
    content = f"""---
updated: "{today}"
birth_year: {BIRTH_YEAR}
---

# 夢・やりたいことリスト

## 結果レベル

## 実現レベル

## 基礎レベル

## 未分類

## 達成済み
"""
    _write_dreams(content)
    return content


def _parse_dreams(content: str) -> list:
    """Parse all dreams from dreams.md."""
    dreams = []
    for m in DREAM_PATTERN.finditer(content):
        dreams.append({
            "completed": m.group(1) == "x",
            "title": m.group(2),
            "category": m.group(3),
            "priority": m.group(4),
            "progress": int(m.group(5)),
            "target_date": m.group(6),
            "registered": m.group(7),
            "goals": m.group(8) if m.group(8) else "",
        })
    return dreams


def _category_to_section(category: str) -> str:
    """Map category to section header."""
    info = PYRAMID_CATEGORIES.get(category, PYRAMID_CATEGORIES["未分類"])
    level = info["level"]
    if level == "未分類":
        return "## 未分類"
    return f"## {level}"


def _current_age() -> int:
    today = date.today()
    age = today.year - BIRTH_YEAR
    # Approximate: if before birthday month, subtract 1
    return age


def add_dream(
    title: str,
    category: str = "未分類",
    priority: str = "B",
    target_date: str = "",
    goals: str = "",
) -> str:
    """Add a new dream/goal."""
    try:
        content = _read_dreams()
        if not content:
            content = _init_dreams_file()

        today = date.today().isoformat()
        if not target_date:
            target_date = "未定"

        # Validate category
        if category not in PYRAMID_CATEGORIES:
            category = "未分類"

        # Validate priority
        if priority not in ("A", "B", "C"):
            priority = "B"

        new_line = (
            f"- [ ] {title} | カテゴリ: {category} | 優先度: {priority} "
            f"| 進捗: 0% | 実現予定: {target_date} | 登録: {today}"
        )
        if goals:
            new_line += f"\n  目標: {goals}"

        section = _category_to_section(category)
        if section in content:
            content = content.replace(section, f"{section}\n{new_line}", 1)
        else:
            # Add before 達成済み
            if "## 達成済み" in content:
                content = content.replace("## 達成済み", f"{section}\n{new_line}\n\n## 達成済み")
            else:
                content += f"\n{section}\n{new_line}\n"

        content = re.sub(
            r'updated: "\d{4}-\d{2}-\d{2}"',
            f'updated: "{today}"',
            content,
        )
        _write_dreams(content)

        cat_info = PYRAMID_CATEGORIES.get(category, {})
        emoji = cat_info.get("emoji", "📌")
        return (
            f"{emoji} 夢を追加しました: **{title}**\n"
            f"カテゴリ: {category} | 優先度: {priority} | 実現予定: {target_date}"
        )
    except Exception as e:
        logger.error(f"add_dream error: {e}")
        return f"夢の追加に失敗しました: {e}"


def list_dreams(category: str = "", status: str = "active") -> str:
    """List dreams. Filter by category and/or status (active/completed/all)."""
    try:
        content = _read_dreams()
        if not content:
            return "夢・やりたいことはまだ登録されていません。「夢を追加して」と話しかけてください。"

        dreams = _parse_dreams(content)
        if not dreams:
            return "夢・やりたいことはまだ登録されていません。「夢を追加して」と話しかけてください。"

        # Filter
        if status == "active":
            dreams = [d for d in dreams if not d["completed"]]
        elif status == "completed":
            dreams = [d for d in dreams if d["completed"]]

        if category:
            dreams = [d for d in dreams if d["category"] == category]

        if not dreams:
            return f"条件に合う夢が見つかりませんでした。（フィルタ: カテゴリ={category or '全て'}, 状態={status}）"

        # Sort by priority then progress
        priority_order = {"A": 0, "B": 1, "C": 2}
        dreams.sort(key=lambda d: (priority_order.get(d["priority"], 9), -d["progress"]))

        lines = [f"# 🌟 夢・やりたいことリスト（{len(dreams)}件）\n"]

        for d in dreams:
            cat_info = PYRAMID_CATEGORIES.get(d["category"], {})
            emoji = cat_info.get("emoji", "📌")
            check = "✅" if d["completed"] else "⬜"

            # Progress bar
            filled = d["progress"] // 10
            bar = "█" * filled + "░" * (10 - filled)

            target = f" → {d['target_date']}" if d["target_date"] != "未定" else ""
            lines.append(
                f"{check} **{d['title']}** [{d['priority']}]\n"
                f"  {emoji} {d['category']} | {bar} {d['progress']}%{target}"
            )
            if d.get("goals"):
                lines.append(f"  🎯 {d['goals']}")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"list_dreams error: {e}")
        return f"夢リストの取得に失敗しました: {e}"


def update_dream(
    keyword: str,
    progress: Optional[int] = None,
    target_date: Optional[str] = None,
    priority: Optional[str] = None,
    goals: Optional[str] = None,
) -> str:
    """Update a dream's progress, target date, priority, or goals."""
    try:
        content = _read_dreams()
        if not content:
            return "夢リストが空です。"

        lines = content.split("\n")
        found = False
        updated_title = ""

        for i, line in enumerate(lines):
            if keyword in line and line.strip().startswith("- [ ]"):
                if progress is not None:
                    progress = max(0, min(100, progress))
                    line = re.sub(r"進捗: \d+%", f"進捗: {progress}%", line)
                if target_date is not None:
                    line = re.sub(r"実現予定: \S+", f"実現予定: {target_date}", line)
                if priority is not None and priority in ("A", "B", "C"):
                    line = re.sub(r"優先度: [A-C]", f"優先度: {priority}", line)
                lines[i] = line

                # Handle goals update
                if goals is not None:
                    # Check if next line is a goal line
                    if i + 1 < len(lines) and lines[i + 1].strip().startswith("目標:"):
                        lines[i + 1] = f"  目標: {goals}"
                    else:
                        lines.insert(i + 1, f"  目標: {goals}")

                m = re.match(r"^- \[ \] (.+?) \|", line)
                updated_title = m.group(1) if m else keyword
                found = True
                break

        if not found:
            return f"「{keyword}」に一致する夢が見つかりませんでした。"

        content = "\n".join(lines)
        content = re.sub(
            r'updated: "\d{4}-\d{2}-\d{2}"',
            f'updated: "{date.today().isoformat()}"',
            content,
        )
        _write_dreams(content)

        parts = [f"「{updated_title}」を更新しました"]
        if progress is not None:
            parts.append(f"進捗: {progress}%")
        if target_date is not None:
            parts.append(f"実現予定: {target_date}")
        if priority is not None:
            parts.append(f"優先度: {priority}")
        return " | ".join(parts)
    except Exception as e:
        logger.error(f"update_dream error: {e}")
        return f"夢の更新に失敗しました: {e}"


def complete_dream(keyword: str) -> str:
    """Mark a dream as achieved."""
    try:
        content = _read_dreams()
        if not content:
            return "夢リストが空です。"

        lines = content.split("\n")
        completed_title = None
        completed_line = None
        remove_indices = []

        for i, line in enumerate(lines):
            if keyword in line and line.strip().startswith("- [ ]"):
                m = re.match(r"^- \[ \] (.+?) \|", line)
                completed_title = m.group(1) if m else keyword
                today = date.today().isoformat()
                # Change to completed
                completed_line = line.replace("- [ ]", "- [x]")
                completed_line = re.sub(r"進捗: \d+%", "進捗: 100%", completed_line)
                remove_indices.append(i)
                # Check if next line is goals
                if i + 1 < len(lines) and lines[i + 1].strip().startswith("目標:"):
                    remove_indices.append(i + 1)
                break

        if not completed_title:
            return f"「{keyword}」に一致する夢が見つかりませんでした。"

        # Remove from original position
        new_lines = [l for idx, l in enumerate(lines) if idx not in remove_indices]
        content = "\n".join(new_lines)

        # Add to 達成済み section
        if "## 達成済み" in content:
            content = content.replace("## 達成済み", f"## 達成済み\n{completed_line}", 1)
        else:
            content += f"\n## 達成済み\n{completed_line}\n"

        content = re.sub(
            r'updated: "\d{4}-\d{2}-\d{2}"',
            f'updated: "{date.today().isoformat()}"',
            content,
        )
        _write_dreams(content)
        return f"🎉 おめでとうございます！「{completed_title}」を達成しました！"
    except Exception as e:
        logger.error(f"complete_dream error: {e}")
        return f"夢の完了処理に失敗しました: {e}"


def get_pyramid_summary() -> str:
    """Get Life Pyramid summary — dreams grouped by pyramid level."""
    try:
        content = _read_dreams()
        if not content:
            return "夢リストが空です。ピラミッドを構築するには夢を追加してください。"

        dreams = [d for d in _parse_dreams(content) if not d["completed"]]
        if not dreams:
            return "アクティブな夢がありません。「夢を追加して」と話しかけてください。"

        # Group by level
        levels = {"結果レベル": [], "実現レベル": [], "基礎レベル": [], "未分類": []}
        for d in dreams:
            cat_info = PYRAMID_CATEGORIES.get(d["category"], PYRAMID_CATEGORIES["未分類"])
            level = cat_info["level"]
            levels[level].append(d)

        lines = ["# 🔺 夢・人生ピラミッド\n"]

        # Category counts for balance check
        cat_counts = {}
        for d in dreams:
            cat_counts[d["category"]] = cat_counts.get(d["category"], 0) + 1

        # Display pyramid (top to bottom)
        for level_name in ["結果レベル", "実現レベル", "基礎レベル"]:
            level_dreams = levels[level_name]
            # Get categories in this level
            level_cats = [
                cat for cat, info in PYRAMID_CATEGORIES.items()
                if info["level"] == level_name
            ]

            lines.append(f"### {'🔴' if level_name == '結果レベル' else '🟡' if level_name == '実現レベル' else '🟢'} {level_name}")
            for cat in level_cats:
                emoji = PYRAMID_CATEGORIES[cat]["emoji"]
                cat_dreams = [d for d in level_dreams if d["category"] == cat]
                count = len(cat_dreams)
                lines.append(f"  {emoji} **{cat}**: {count}件")
                for d in cat_dreams:
                    filled = d["progress"] // 10
                    bar = "█" * filled + "░" * (10 - filled)
                    lines.append(f"    [{d['priority']}] {d['title']} {bar} {d['progress']}%")
            lines.append("")

        if levels["未分類"]:
            lines.append(f"### 📌 未分類: {len(levels['未分類'])}件")
            for d in levels["未分類"]:
                lines.append(f"  - {d['title']}（カテゴリを設定してください）")
            lines.append("")

        # Balance analysis
        empty_cats = [
            cat for cat in PYRAMID_CATEGORIES
            if cat != "未分類" and cat_counts.get(cat, 0) == 0
        ]
        if empty_cats:
            lines.append("⚠️ **バランス注意** — 以下の分野に夢がありません:")
            for cat in empty_cats:
                emoji = PYRAMID_CATEGORIES[cat]["emoji"]
                lines.append(f"  {emoji} {cat}")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"get_pyramid_summary error: {e}")
        return f"ピラミッドの取得に失敗しました: {e}"


def get_future_timeline(year: Optional[int] = None) -> str:
    """Get future timeline — dreams mapped by target year/age."""
    try:
        content = _read_dreams()
        if not content:
            return "夢リストが空です。"

        dreams = [d for d in _parse_dreams(content) if not d["completed"]]
        if not dreams:
            return "アクティブな夢がありません。"

        current_year = date.today().year
        age = _current_age()

        # Group by target year
        by_year = {"未定": []}
        for d in dreams:
            td = d["target_date"]
            if td == "未定":
                by_year["未定"].append(d)
            else:
                try:
                    y = td[:4]  # Extract year from YYYY-MM-DD or YYYY
                    by_year.setdefault(y, []).append(d)
                except (ValueError, IndexError):
                    by_year["未定"].append(d)

        # If specific year requested, filter
        if year:
            target_dreams = by_year.get(str(year), [])
            target_age = age + (year - current_year)
            if not target_dreams:
                return f"{year}年（{target_age}歳）に予定された夢はありません。"
            lines = [f"# 📅 {year}年 — ロキ（{target_age}歳）\n"]
            for d in target_dreams:
                emoji = PYRAMID_CATEGORIES.get(d["category"], {}).get("emoji", "📌")
                filled = d["progress"] // 10
                bar = "█" * filled + "░" * (10 - filled)
                lines.append(f"{emoji} **{d['title']}** [{d['priority']}] {bar} {d['progress']}%")
            return "\n".join(lines)

        # Full timeline
        lines = [f"# 📅 未来年表 — ロキ（現在{age}歳）\n"]

        sorted_years = sorted(
            [y for y in by_year if y != "未定"],
            key=lambda y: int(y),
        )

        for y in sorted_years:
            y_int = int(y)
            target_age = age + (y_int - current_year)
            year_dreams = by_year[y]
            lines.append(f"### {y}年（{target_age}〜{target_age + 1}歳）")
            for d in year_dreams:
                emoji = PYRAMID_CATEGORIES.get(d["category"], {}).get("emoji", "📌")
                lines.append(f"  {emoji} {d['title']} [{d['priority']}] 進捗{d['progress']}%")
            lines.append("")

        if by_year["未定"]:
            lines.append("### 🔮 時期未定")
            for d in by_year["未定"]:
                emoji = PYRAMID_CATEGORIES.get(d["category"], {}).get("emoji", "📌")
                lines.append(f"  {emoji} {d['title']} [{d['priority']}]")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"get_future_timeline error: {e}")
        return f"未来年表の取得に失敗しました: {e}"


def get_dream_briefing() -> str:
    """Get a compact dream summary for morning briefing."""
    try:
        content = _read_dreams()
        if not content:
            return ""

        dreams = [d for d in _parse_dreams(content) if not d["completed"]]
        if not dreams:
            return ""

        total = len(dreams)
        priority_a = [d for d in dreams if d["priority"] == "A"]

        # Category balance
        cat_counts = {}
        for d in dreams:
            cat_counts[d["category"]] = cat_counts.get(d["category"], 0) + 1

        empty_cats = [
            cat for cat in PYRAMID_CATEGORIES
            if cat != "未分類" and cat_counts.get(cat, 0) == 0
        ]

        # Find dreams with upcoming deadlines
        today = date.today()
        upcoming = []
        for d in dreams:
            if d["target_date"] != "未定":
                try:
                    td = date.fromisoformat(d["target_date"])
                    days_left = (td - today).days
                    if 0 <= days_left <= 30:
                        upcoming.append((d, days_left))
                except ValueError:
                    pass

        lines = [f"🔺 **ピラミッド**: {total}件の夢"]

        # Category summary
        cat_parts = []
        for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
            emoji = PYRAMID_CATEGORIES.get(cat, {}).get("emoji", "📌")
            cat_parts.append(f"{emoji}{cat}{count}件")
        lines.append("  " + " / ".join(cat_parts))

        if empty_cats:
            lines.append(f"  ⚠️ 空の分野: {', '.join(empty_cats)}")

        if priority_a:
            lines.append(f"⭐ **優先度A**: {', '.join(d['title'] for d in priority_a)}")

        if upcoming:
            upcoming.sort(key=lambda x: x[1])
            for d, days in upcoming[:3]:
                lines.append(f"  ⏰ **{d['title']}** — あと{days}日（進捗{d['progress']}%）")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"get_dream_briefing error: {e}")
        return ""
