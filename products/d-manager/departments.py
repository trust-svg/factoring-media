"""Department AI personality loader."""

from pathlib import Path
from typing import Optional
import config


def load_department_prompt(department: str) -> str:
    """Load CLAUDE.md for a department as system prompt."""
    # Load company-wide rules
    company_rules = ""
    company_claude = config.COMPANY_DIR / "CLAUDE.md"
    if company_claude.exists():
        company_rules = company_claude.read_text(encoding="utf-8")

    # Load department-specific CLAUDE.md
    dept_claude = config.COMPANY_DIR / department / "CLAUDE.md"
    dept_prompt = ""
    if dept_claude.exists():
        dept_prompt = dept_claude.read_text(encoding="utf-8")

    # Load agent files if they exist
    agents_dir = config.COMPANY_DIR / department / "agents"
    agent_prompts = ""
    if agents_dir.exists():
        for agent_file in agents_dir.glob("*.md"):
            agent_prompts += f"\n\n{agent_file.read_text(encoding='utf-8')}"

    # Load shared skills
    skills_dir = config.COMPANY_DIR / "skills"
    skills_text = ""
    if skills_dir.exists():
        for skill_file in skills_dir.glob("*.md"):
            skills_text += f"\n\n{skill_file.read_text(encoding='utf-8')}"

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
