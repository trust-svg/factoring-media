"""人物DB — `.company/secretary/people/<slug>.md` を読み書きする。

各人物に1ファイル。フォーマット:
---
name: 山田太郎
company: ○○株式会社
slug: yamada-taro
created: 2026-05-01
---

# 山田太郎（○○株式会社）

## 接触履歴
- 2026-05-01 14:00 — 商談MTG（カレンダー）
- 2026-04-20 — メールやり取り（件名: ...）

## メモ

<!-- 自由記述 -->
"""

import logging
import re
import unicodedata
from datetime import date
from typing import Optional

import config

logger = logging.getLogger(__name__)
PEOPLE_DIR = config.COMPANY_DIR / "secretary" / "people"


def _slugify(name: str) -> str:
    """Convert a name to a filesystem-safe slug.

    Japanese names: keep as-is but replace spaces/symbols.
    """
    s = unicodedata.normalize("NFKC", name).strip()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^\w\-ぁ-んァ-ヶー一-龯]", "", s)
    return s.lower() if s.isascii() else s


def person_path(name: str) -> "config.Path":
    """Return the file path for a person record."""
    return PEOPLE_DIR / f"{_slugify(name)}.md"


def upsert_person(
    name: str,
    company: Optional[str] = None,
    contact_summary: Optional[str] = None,
    note: Optional[str] = None,
) -> str:
    """Create or update a person file. Appends a contact entry if provided.

    Returns the file path.
    """
    PEOPLE_DIR.mkdir(parents=True, exist_ok=True)
    path = person_path(name)
    today = date.today().isoformat()

    if not path.exists():
        slug = _slugify(name)
        title = f"{name}（{company}）" if company else name
        content = (
            f"---\nname: {name}\ncompany: {company or ''}\nslug: {slug}\n"
            f"created: {today}\n---\n\n"
            f"# {title}\n\n"
            f"## 接触履歴\n\n"
            f"## メモ\n\n"
        )
        path.write_text(content, encoding="utf-8")
        logger.info(f"Created person file: {path}")

    content = path.read_text(encoding="utf-8")

    # Append contact entry under "## 接触履歴"
    if contact_summary:
        entry = f"- {today} — {contact_summary.strip()}"
        content = re.sub(
            r"(## 接触履歴\n)(.*?)(\n## |\Z)",
            lambda m: f"{m.group(1)}{m.group(2).rstrip()}\n{entry}\n{m.group(3)}",
            content,
            count=1,
            flags=re.DOTALL,
        )

    # Append note under "## メモ"
    if note:
        note_entry = f"- {today}: {note.strip()}"
        content = re.sub(
            r"(## メモ\n)(.*?)(\n## |\Z)",
            lambda m: f"{m.group(1)}{m.group(2).rstrip()}\n{note_entry}\n{m.group(3)}",
            content,
            count=1,
            flags=re.DOTALL,
        )

    # Update company in frontmatter if provided and currently empty
    if company:
        content = re.sub(
            r"^company:\s*$",
            f"company: {company}",
            content,
            count=1,
            flags=re.MULTILINE,
        )

    path.write_text(content, encoding="utf-8")
    return str(path)


def list_people() -> list[dict]:
    """Return a list of all people records."""
    if not PEOPLE_DIR.exists():
        return []
    out = []
    for p in PEOPLE_DIR.glob("*.md"):
        text = p.read_text(encoding="utf-8")
        name_m = re.search(r"^name:\s*(.+)$", text, re.MULTILINE)
        company_m = re.search(r"^company:\s*(.+)$", text, re.MULTILINE)
        out.append(
            {
                "slug": p.stem,
                "name": name_m.group(1).strip() if name_m else p.stem,
                "company": (company_m.group(1).strip() if company_m else ""),
                "path": str(p),
            }
        )
    return out
