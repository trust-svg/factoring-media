"""キーワード抽出・分析ユーティリティ"""
from __future__ import annotations

import re
from collections import Counter

# eBayタイトルで無駄とされるパターン
SPAM_PATTERNS = [
    r"L@@K",
    r"WOW",
    r"!!!+",
    r"\*\*\*+",
    r"LOOK",
    r"RARE!+",
    r"AMAZING",
    r"GREAT!+",
    r"MUST SEE",
    r"DON'T MISS",
]

# eBayタイトルで一般的に使われる有効な略語
VALID_ABBREVIATIONS = {
    "w/", "nr", "exc", "exc+", "exc++", "exc+++",
    "mint", "mint-", "cla", "cla'd",
    "s/n", "sn", "n/a", "oem", "nos",
    "slr", "dslr", "af", "mf",
}

# タイトルから除外するストップワード
STOP_WORDS = {
    "the", "a", "an", "and", "or", "for", "with", "from", "in", "on", "to",
    "of", "is", "it", "by", "at", "as", "this", "that", "be", "has", "have",
    "are", "was", "were", "been",
}


def extract_keywords(text: str) -> list[str]:
    """テキストからキーワードを抽出する"""
    cleaned = re.sub(r'[^\w\s/\-&+\']', ' ', text)
    words = cleaned.split()
    return [
        w for w in words
        if w.lower() not in STOP_WORDS and len(w) >= 2
    ]


def find_spam_patterns(title: str) -> list[str]:
    """タイトル内のスパムパターンを検出する"""
    found = []
    for pattern in SPAM_PATTERNS:
        if re.search(pattern, title, re.IGNORECASE):
            found.append(pattern)
    return found


def find_excessive_caps(title: str) -> bool:
    """過剰な大文字使用を検出する（全体の70%以上がアルファベット大文字）"""
    alpha_chars = [c for c in title if c.isalpha()]
    if not alpha_chars:
        return False
    upper_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
    return upper_ratio > 0.7


def calculate_keyword_density(text: str, keywords: list[str]) -> dict[str, float]:
    """テキスト内のキーワード密度を計算する"""
    words = text.lower().split()
    total = len(words)
    if total == 0:
        return {}
    return {
        kw: words.count(kw.lower()) / total
        for kw in keywords
        if kw.lower() in words
    }


def find_missing_keywords(
    title: str, competitor_keywords: list[str]
) -> list[str]:
    """自分のタイトルに欠けている競合キーワードを見つける"""
    own_words = {w.lower() for w in extract_keywords(title)}
    return [
        kw for kw in competitor_keywords
        if kw.lower() not in own_words
    ]


def suggest_keyword_additions(
    title: str, missing_keywords: list[str], max_len: int = 80
) -> list[str]:
    """タイトルに追加可能なキーワードを提案する（文字数制限考慮）"""
    remaining = max_len - len(title)
    suggestions = []
    for kw in missing_keywords:
        needed = len(kw) + 1  # スペース分
        if needed <= remaining:
            suggestions.append(kw)
            remaining -= needed
    return suggestions
