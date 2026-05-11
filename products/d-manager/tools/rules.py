"""rules.md operations — read, append, list rules."""

import logging
import re
from datetime import date

import config

logger = logging.getLogger(__name__)
RULES_PATH = config.COMPANY_DIR / "secretary" / "rules.md"


def read_rules() -> str:
    """Return raw rules.md content."""
    if not RULES_PATH.exists():
        return ""
    return RULES_PATH.read_text(encoding="utf-8")


def add_rule(category: str, rule_text: str) -> str:
    """Append a rule under the given category section.

    If section exists, append. If not, create new section before "## その他".
    Returns a confirmation message.
    """
    if not RULES_PATH.exists():
        return f"⚠️ rules.md not found at {RULES_PATH}"

    content = RULES_PATH.read_text(encoding="utf-8")
    rule_text = rule_text.strip()
    if not rule_text:
        return "⚠️ ルール内容が空です"

    rule_line = f"- {rule_text}"
    section_pattern = re.compile(rf"^## {re.escape(category)}\s*\n", re.MULTILINE)
    match = section_pattern.search(content)

    if match:
        # Find the next "## " heading or end-of-file
        section_start = match.end()
        next_heading = re.search(r"^## ", content[section_start:], re.MULTILINE)
        if next_heading:
            insert_pos = section_start + next_heading.start()
            # Insert before next heading, preserving blank line
            before = content[:insert_pos].rstrip()
            after = content[insert_pos:]
            new_content = f"{before}\n{rule_line}\n\n{after}"
        else:
            new_content = content.rstrip() + f"\n{rule_line}\n"
    else:
        # Insert new section before "## その他" if exists, else at end
        other_match = re.search(r"^## その他", content, re.MULTILINE)
        new_section = f"## {category}\n\n{rule_line}\n\n"
        if other_match:
            insert_pos = other_match.start()
            new_content = content[:insert_pos] + new_section + content[insert_pos:]
        else:
            new_content = content.rstrip() + f"\n\n{new_section}"

    # Update frontmatter date
    new_content = re.sub(
        r'updated: "\d{4}-\d{2}-\d{2}"',
        f'updated: "{date.today().isoformat()}"',
        new_content,
    )

    RULES_PATH.write_text(new_content, encoding="utf-8")
    logger.info(f"Rule added to [{category}]: {rule_text[:60]}")
    return f"✅ 「{category}」セクションに追加しました:\n- {rule_text}"


def list_categories() -> list[str]:
    """List all category headings in rules.md."""
    content = read_rules()
    return re.findall(r"^## (.+)$", content, re.MULTILINE)
