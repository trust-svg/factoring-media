"""SEOスコアリングエンジン"""
from __future__ import annotations

import json
import re

from config import (
    EBAY_TITLE_MAX_LENGTH,
    MIN_DESCRIPTION_LENGTH,
    RECOMMENDED_PHOTO_COUNT,
    SEO_WEIGHTS,
)
from analyzer.keywords import find_excessive_caps, find_spam_patterns


def score_listing(listing) -> dict:
    """
    出品のSEOスコアを計算する。
    listing: database.models.Listing オブジェクト

    戻り値: {
        "overall": int,
        "title_score": int,
        "description_score": int,
        "specifics_score": int,
        "photo_score": int,
        "issues": list[str],
        "suggestions": list[str],
    }
    """
    issues: list[str] = []
    suggestions: list[str] = []

    title_score = _score_title(listing.title, issues, suggestions)
    description_score = _score_description(
        listing.description or "", issues, suggestions
    )
    specifics_score = _score_item_specifics(
        listing.item_specifics_json, issues, suggestions
    )
    photo_score = _score_photos(
        listing.image_urls_json, issues, suggestions
    )

    overall = int(
        title_score * SEO_WEIGHTS["title"]
        + description_score * SEO_WEIGHTS["description"]
        + specifics_score * SEO_WEIGHTS["specifics"]
        + photo_score * SEO_WEIGHTS["photos"]
    )

    return {
        "overall": overall,
        "title_score": title_score,
        "description_score": description_score,
        "specifics_score": specifics_score,
        "photo_score": photo_score,
        "issues": issues,
        "suggestions": suggestions,
    }


def _score_title(title: str, issues: list, suggestions: list) -> int:
    """タイトルスコア（0-100）"""
    score = 100
    title_len = len(title)

    # 文字数活用率
    if title_len == 0:
        issues.append("Title is empty")
        return 0

    usage_ratio = title_len / EBAY_TITLE_MAX_LENGTH
    if usage_ratio < 0.5:
        penalty = int((0.5 - usage_ratio) * 60)
        score -= penalty
        issues.append(
            f"Title only uses {title_len}/{EBAY_TITLE_MAX_LENGTH} characters "
            f"({int(usage_ratio * 100)}% utilization)"
        )
        suggestions.append(
            f"Add more keywords to fill the {EBAY_TITLE_MAX_LENGTH}-char limit"
        )
    elif usage_ratio < 0.75:
        penalty = int((0.75 - usage_ratio) * 30)
        score -= penalty
        suggestions.append(
            f"Title uses {title_len}/{EBAY_TITLE_MAX_LENGTH} chars — "
            f"consider adding more keywords"
        )

    # スパムパターン検出
    spam = find_spam_patterns(title)
    if spam:
        score -= 15 * len(spam)
        issues.append(f"Title contains spam patterns: {', '.join(spam)}")
        suggestions.append("Remove spam patterns — they hurt search ranking")

    # 過剰大文字
    if find_excessive_caps(title):
        score -= 15
        issues.append("Title has excessive capitalization (>70% uppercase)")
        suggestions.append("Use normal capitalization for better readability")

    # 特殊文字の多用
    special_count = len(re.findall(r'[!@#$%^&*()_+=\[\]{}|\\<>~`]', title))
    if special_count > 3:
        score -= 10
        issues.append(f"Title contains {special_count} special characters")

    return max(0, min(100, score))


def _score_description(
    description: str, issues: list, suggestions: list
) -> int:
    """説明文スコア（0-100）"""
    score = 100
    desc_len = len(description.strip())

    if desc_len == 0:
        issues.append("Description is empty")
        suggestions.append("Add a detailed product description")
        return 0

    # 最小文字数
    if desc_len < MIN_DESCRIPTION_LENGTH:
        penalty = int((1 - desc_len / MIN_DESCRIPTION_LENGTH) * 40)
        score -= penalty
        issues.append(
            f"Description is too short ({desc_len} chars, "
            f"recommended: {MIN_DESCRIPTION_LENGTH}+)"
        )
        suggestions.append("Add more product details to the description")

    # HTML構造チェック
    has_html = bool(re.search(r'<[a-z][\s\S]*?>', description, re.IGNORECASE))
    if not has_html and desc_len > 50:
        score -= 10
        suggestions.append(
            "Use HTML formatting (headers, lists, bold) for better presentation"
        )

    # キーワード存在チェック（基本的な商品属性ワード）
    useful_sections = ["condition", "shipping", "return", "specification",
                       "feature", "include", "detail", "description"]
    found_sections = sum(
        1 for s in useful_sections if s.lower() in description.lower()
    )
    if found_sections == 0 and desc_len > 100:
        score -= 10
        suggestions.append(
            "Include sections like condition, specifications, or shipping info"
        )

    return max(0, min(100, score))


def _score_item_specifics(
    specifics_json: str, issues: list, suggestions: list
) -> int:
    """Item Specificsスコア（0-100）"""
    try:
        specifics = json.loads(specifics_json)
    except (json.JSONDecodeError, TypeError):
        specifics = {}

    if not specifics:
        issues.append("No Item Specifics filled in")
        suggestions.append("Add Item Specifics (Brand, Model, Type, etc.)")
        return 0

    score = 100
    count = len(specifics)

    # 基本的な必須項目
    essential_keys = {"Brand", "brand", "MPN", "mpn", "Type", "type", "Model", "model"}
    filled_essential = sum(
        1 for key in specifics if key in essential_keys or key.lower() in {k.lower() for k in essential_keys}
    )

    if filled_essential == 0:
        score -= 30
        issues.append("Missing essential Item Specifics (Brand, Model, Type, MPN)")
        suggestions.append("Fill in at least Brand and Model in Item Specifics")
    elif filled_essential < 2:
        score -= 15
        suggestions.append("Add more essential Item Specifics (Brand, Model, Type)")

    # 項目数ベースの評価
    if count < 3:
        score -= 20
        issues.append(f"Only {count} Item Specifics filled (recommend 5+)")
    elif count < 5:
        score -= 10
        suggestions.append(f"{count} Item Specifics filled — consider adding more")

    return max(0, min(100, score))


def _score_photos(
    image_urls_json: str, issues: list, suggestions: list
) -> int:
    """写真スコア（0-100）"""
    try:
        image_urls = json.loads(image_urls_json)
    except (json.JSONDecodeError, TypeError):
        image_urls = []

    count = len(image_urls)

    if count == 0:
        issues.append("No photos")
        suggestions.append("Add at least 1 product photo")
        return 0

    if count < RECOMMENDED_PHOTO_COUNT:
        # 1枚=40点, 2枚=55点, 3枚=70点, 4枚=85点
        score = 25 + (count * 15)
        issues.append(
            f"Only {count} photo(s) (recommend {RECOMMENDED_PHOTO_COUNT}+)"
        )
        suggestions.append(f"Add more photos (currently {count}, recommend {RECOMMENDED_PHOTO_COUNT}+)")
        return min(100, score)

    return 100
