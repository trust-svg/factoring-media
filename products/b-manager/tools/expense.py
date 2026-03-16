"""Expense tracking tool — records expenses to daily files."""

import re
from datetime import date, datetime
from pathlib import Path
from typing import List, Dict

from config import SECRETARY_DIR

EXPENSE_DIR = SECRETARY_DIR / "expenses"


def _month_file() -> Path:
    EXPENSE_DIR.mkdir(parents=True, exist_ok=True)
    return EXPENSE_DIR / f"{date.today().strftime('%Y-%m')}.md"


def record_expense(description: str, amount: int, category: str = "その他") -> str:
    """Record an expense entry."""
    f = _month_file()
    now = datetime.now()

    if not f.exists():
        header = f"""---
month: "{now.strftime('%Y-%m')}"
type: expense
---

# 経費記録 — {now.strftime('%Y年%m月')}

"""
        f.write_text(header, encoding="utf-8")

    entry = f"| {now.strftime('%m/%d')} | {description} | {category} | ¥{amount:,} |\n"

    content = f.read_text(encoding="utf-8")
    # Add table header if first entry of the month
    if "| 日付 |" not in content:
        content += "| 日付 | 内容 | カテゴリ | 金額 |\n|---|---|---|---|\n"

    content += entry
    f.write_text(content, encoding="utf-8")

    return f"記録しました: {description} ¥{amount:,}（{category}）"


def get_expense_summary(month: str = "") -> Dict:
    """Get expense summary for a month (default: current month)."""
    if not month:
        month = date.today().strftime("%Y-%m")

    f = EXPENSE_DIR / f"{month}.md"
    if not f.exists():
        return {"month": month, "total": 0, "count": 0, "by_category": {}}

    content = f.read_text(encoding="utf-8")
    lines = content.splitlines()

    total = 0
    count = 0
    by_category: Dict[str, int] = {}

    for line in lines:
        match = re.match(r'\| \d+/\d+ \| .+ \| (.+) \| ¥([\d,]+) \|', line)
        if match:
            cat = match.group(1).strip()
            amt = int(match.group(2).replace(",", ""))
            total += amt
            count += 1
            by_category[cat] = by_category.get(cat, 0) + amt

    return {
        "month": month,
        "total": total,
        "count": count,
        "by_category": by_category,
    }
