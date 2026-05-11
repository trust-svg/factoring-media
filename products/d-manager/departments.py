"""Department AI personality loader."""

from __future__ import annotations

from pathlib import Path

import config


def _iter_skill_bodies(skills_dir: Path):
    """`.company/skills/` 配下のスキル本文を順に yield する。

    - `<name>.md`（フラット形式）→ 全文。
    - `<name>/SKILL.md`（新形式）→ SKILL.md の本文のみ（同ディレクトリの references/ は連結しない）。
    - 同名で両方ある場合は `<name>/SKILL.md` を優先。
    - 先頭が `.` のエントリ（`.archive` / `.snapshots` 等）は無視。
    """
    if not skills_dir.exists():
        return
    # まず新形式のディレクトリ名を集める（フラット側を抑止するため）
    dir_skills = {}
    for entry in sorted(skills_dir.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            skill_md = entry / "SKILL.md"
            if skill_md.exists():
                dir_skills[entry.name] = skill_md
    for name, skill_md in dir_skills.items():
        yield skill_md.read_text(encoding="utf-8")
    for entry in sorted(skills_dir.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_file() and entry.suffix == ".md":
            if entry.stem in dir_skills:
                continue  # 新形式が優先
            yield entry.read_text(encoding="utf-8")


def skills_concat_size() -> dict:
    """system prompt に連結される skills 部分の規模（メトリクス用）。"""
    skills_dir = config.COMPANY_DIR / "skills"
    count = 0
    chars = 0
    for body in _iter_skill_bodies(skills_dir):
        count += 1
        chars += len(body)
    return {"count": count, "concat_chars": chars}


def load_department_prompt(department: str) -> str:
    """Load CLAUDE.md for a department as system prompt."""
    company_rules = ""
    company_claude = config.COMPANY_DIR / "CLAUDE.md"
    if company_claude.exists():
        company_rules = company_claude.read_text(encoding="utf-8")

    dept_claude = config.COMPANY_DIR / department / "CLAUDE.md"
    dept_prompt = ""
    if dept_claude.exists():
        dept_prompt = dept_claude.read_text(encoding="utf-8")

    agents_dir = config.COMPANY_DIR / department / "agents"
    agent_prompts = ""
    if agents_dir.exists():
        for agent_file in sorted(agents_dir.glob("*.md")):
            agent_prompts += f"\n\n{agent_file.read_text(encoding='utf-8')}"

    skills_dir = config.COMPANY_DIR / "skills"
    skills_text = ""
    for body in _iter_skill_bodies(skills_dir):
        skills_text += f"\n\n{body}"

    return f"""{company_rules}

---

{dept_prompt}

{agent_prompts}

---

## 共通スキル
{skills_text}
"""


def get_department_for_channel(channel_name: str) -> str:
    """Map Discord channel name to department."""
    return config.CHANNEL_MAP.get(channel_name, "secretary")
