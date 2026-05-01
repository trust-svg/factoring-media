"""プロンプト安全性検査。実在人物名・著名人参照をブロックする。"""

from __future__ import annotations

BLOCK_WORDS: tuple[str, ...] = (
    "aragaki",
    "yui",
    "ishihara",
    "satomi",
    "ayase",
    "haruka",
    "toda",
    "erika",
    "kitagawa",
    "keiko",
    "takeuchi",
    "yuuko",
    "綾瀬",
    "新垣",
    "石原",
    "戸田",
    "北川",
    "竹内",
    "celebrity",
    "idol",
    "actress",
    "actor",
)


def is_blocked(prompt: str) -> bool:
    """プロンプトに実在人物の名前や不適切なワードが含まれていないか確認。"""
    lower = prompt.lower()
    return any(word in lower for word in BLOCK_WORDS)
