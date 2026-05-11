"""Obsidian Daily Note への秘書ログ追記。

開発日誌は会話終了時にClaude Codeが手動で生成する別系統。
このモジュールは d-manager の夕レビュー時に「秘書ログ」セクションを追記する。
"""

import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

OBSIDIAN_DAILY_DIR = Path.home() / "Obsidian" / "Daily"
SECRETARY_HEADING = "## 🤵 秘書ログ"


def daily_note_path(target_date: Optional[date] = None) -> Path:
    """Return the Obsidian daily note path for the given date (default today)."""
    d = target_date or date.today()
    return OBSIDIAN_DAILY_DIR / f"{d.isoformat()}.md"


def upsert_secretary_section(body: str, target_date: Optional[date] = None) -> str:
    """Insert or replace the 秘書ログ section in today's daily note.

    - If the file doesn't exist: create with minimal frontmatter + section.
    - If section exists: replace contents until next "## " heading or EOF.
    - If section absent: append at end.

    Returns the absolute path written.
    """
    body = body.strip()
    if not body:
        return ""

    path = daily_note_path(target_date)
    OBSIDIAN_DAILY_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%H:%M")
    section = f"{SECRETARY_HEADING}\n_最終更新: {timestamp}_\n\n{body}\n"

    if not path.exists():
        d = (target_date or date.today()).isoformat()
        weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        wd = weekdays[(target_date or date.today()).weekday()]
        content = f"---\ndate: {d}\n---\n\n# {d} ({wd})\n\n{section}"
        path.write_text(content, encoding="utf-8")
        logger.info(f"Created daily note with secretary section: {path}")
        return str(path)

    content = path.read_text(encoding="utf-8")

    # Find existing section
    pattern = re.compile(
        rf"^{re.escape(SECRETARY_HEADING)}\n.*?(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    if pattern.search(content):
        new_content = pattern.sub(section + "\n", content, count=1)
    else:
        new_content = content.rstrip() + f"\n\n{section}"

    path.write_text(new_content, encoding="utf-8")
    logger.info(f"Updated secretary section in {path}")
    return str(path)
