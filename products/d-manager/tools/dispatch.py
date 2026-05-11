"""Agent dispatch system — Steve routes tasks to specialist agents.

Dispatch syntax in Steve's response:
  [→ Elon] 今週のAIトレンドを調査してoutputに保存してください
  [→ Larry] ebay-agentに検索フィルター機能を追加してください

d-manager detects these directives and spawns the target agent
in the background. Results are posted to that agent's channel.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Agent name → department
AGENT_DEPT = {
    "Steve":  "secretary",
    "Jack":   "operations",
    "Jeff":   "operations",
    "Sara":   "operations",
    "Larry":  "product",
    "Tim":    "product",
    "Mary":   "product",
    "Mark":   "marketing",
    "Sheryl": "marketing",
    "Gary":   "marketing",
    "Warren": "finance",
    "Elon":   "research",
    "Reid":   "strategy",
}

# Agent name → Discord channel
AGENT_CHANNEL = {
    "Steve":  "ceo-steve-general",
    "Jack":   "運営-jack-operations",
    "Jeff":   "運営-jack-operations",
    "Sara":   "運営-jack-operations",
    "Larry":  "開発-larry-product",
    "Tim":    "開発-larry-product",
    "Mary":   "開発-larry-product",
    "Mark":   "マーケティング-mark-marketing",
    "Sheryl": "マーケティング-mark-marketing",
    "Gary":   "マーケティング-mark-marketing",
    "Warren": "経理-warren-finance",
    "Elon":   "調査-elon-research",
    "Reid":   "戦略-reid-strategy",
}

# Coding agents run from workspace root, others from COMPANY_DIR
WORKSPACE_AGENTS = {"Larry", "Tim", "Mary"}

_DISPATCH_RE = re.compile(
    r'\[→\s*([A-Za-z]+)\]\s*([\s\S]+?)(?=\[→\s*[A-Za-z]+\]|$)',
)


def parse_dispatches(text: str) -> list[dict]:
    """Extract [→ AgentName] directives from a response.

    Returns list of dicts with keys: agent, department, channel, task, is_coding
    """
    results = []
    for m in _DISPATCH_RE.finditer(text):
        name = m.group(1).strip()
        task = m.group(2).strip()
        if name in AGENT_DEPT and task:
            results.append({
                "agent": name,
                "department": AGENT_DEPT[name],
                "channel": AGENT_CHANNEL.get(name, "ceo-steve-general"),
                "task": task,
                "is_coding": name in WORKSPACE_AGENTS,
            })
    return results


def strip_dispatches(text: str) -> str:
    """Remove [→ ...] blocks from response text (keep rest of message)."""
    return _DISPATCH_RE.sub("", text).strip()
