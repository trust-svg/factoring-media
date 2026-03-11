"""
仕入候補スコアリング＆フィルタリング
ebay-inventory-tool/main.py の pick_best_candidates から移植
"""
import logging
import re

from .image_matcher import compare_images

logger = logging.getLogger(__name__)

# コンディション別スコア（高いほど良い）
CONDITION_SCORES = {
    "ジャンク": 0,
    "現状品": 5,
    "動作未確認": 10,
    "記載なし": 15,
    "中古品": 15,
    "動作確認済": 50,
    "動作品": 50,
    "良品": 70,
    "美品": 85,
    "新品": 100,
    "未使用": 100,
}

# 非本体除外キーワード
EXCLUDE_KEYWORDS = [
    "manual", "マニュアル", "説明書", "取扱説明書",
    "parts only", "パーツのみ", "部品のみ",
    "remote only", "リモコンのみ",
    "cover only", "カバーのみ",
    "cable only", "ケーブルのみ",
]

# 売り切れキーワード
SOLD_OUT_KEYWORDS = [
    "sold", "売り切れ", "販売終了", "取引終了",
]


def _extract_model_tokens(keyword: str) -> list[str]:
    """検索キーワードから型番トークンを抽出（BR-20, CDJ-2000NXS2 等）"""
    tokens = []
    for w in keyword.split():
        if not re.search(r"\d", w):
            continue
        if re.match(r"^\d{1,2}-[A-Za-z]{3,}$", w):
            continue
        if re.match(r"^\d+$", w):
            continue
        if len(w) >= 2:
            tokens.append(w.upper())
    return tokens


def _title_contains_model(title: str, model_tokens: list[str]) -> bool:
    """候補タイトルに全ての型番トークンが含まれるか判定（AND条件）"""
    title_norm = title.upper().replace("−", "-").replace("ー", "-")
    for token in model_tokens:
        found = False
        if token in title_norm:
            found = True
        elif "-" in token and token.replace("-", "") in title_norm.replace("-", ""):
            found = True
        elif re.search(r"[A-Z]", token) and re.search(r"\d", token):
            alpha = re.sub(r"[\d\-]", "", token)
            digits = re.sub(r"[^\d]", "", token)
            if alpha and digits and alpha in title_norm and digits in title_norm:
                found = True
        if not found:
            return False
    return True


def _score_result(result, max_price_jpy: int, search_keyword: str) -> float:
    """仕入候補を0〜100でスコアリング"""
    # 価格スコア (0〜40)
    total = result.price_jpy + (result.shipping_jpy if hasattr(result, 'shipping_jpy') else 0)
    if max_price_jpy > 0 and total > 0:
        price_ratio = total / max_price_jpy
        price_score = max(0, 40 * (1 - price_ratio))
    else:
        price_score = 0

    # コンディションスコア (0〜35)
    cond_raw = CONDITION_SCORES.get(result.condition, 15)
    cond_score = cond_raw / 100 * 35

    # タイトル関連度スコア (0〜25)
    kw_words = [w.lower() for w in search_keyword.split() if len(w) >= 2]
    title_lower = result.title.lower()
    if kw_words:
        match_count = sum(1 for w in kw_words if w in title_lower)
        relevance_score = (match_count / len(kw_words)) * 25
    else:
        relevance_score = 0

    return price_score + cond_score + relevance_score


def pick_best_candidates(
    results: list,
    keyword: str,
    max_price_jpy: int,
    ebay_image_url: str = "",
    top_n: int = 5,
) -> list[dict]:
    """
    仕入候補をスコアリング・フィルタリングし、上位N件を返す。

    Returns:
        スコア付き候補リスト（dict形式、score フィールド付き）
    """
    if not results:
        return []

    # 型番フィルタ
    model_tokens = _extract_model_tokens(keyword)
    if model_tokens:
        before = len(results)
        results = [r for r in results if _title_contains_model(r.title, model_tokens)]
        logger.info(f"  型番フィルタ ({', '.join(model_tokens)}): {before}件 → {len(results)}件")

    # 非本体除外
    before = len(results)
    results = [
        r for r in results
        if not any(ex in r.title.lower() for ex in EXCLUDE_KEYWORDS)
    ]
    if before != len(results):
        logger.info(f"  非本体除外: {before}件 → {len(results)}件")

    # 売り切れ除外
    before = len(results)
    results = [
        r for r in results
        if not any(kw in r.title.lower() for kw in SOLD_OUT_KEYWORDS)
        and not any(kw in r.condition.lower() for kw in SOLD_OUT_KEYWORDS)
    ]
    if before != len(results):
        logger.info(f"  売り切れ除外: {before}件 → {len(results)}件")

    if not results:
        return []

    # スコア計算
    scored = [(r, _score_result(r, max_price_jpy, keyword)) for r in results]
    scored.sort(key=lambda x: x[1], reverse=True)

    # プラットフォーム多様性: 同一プラットフォームは最大2件まで
    pre_selected = []
    platform_count: dict[str, int] = {}
    for r, score in scored:
        pf = r.platform
        if platform_count.get(pf, 0) >= 2:
            continue
        pre_selected.append((r, score))
        platform_count[pf] = platform_count.get(pf, 0) + 1
        if len(pre_selected) >= top_n * 2:
            break

    # AI画像比較
    if ebay_image_url and pre_selected:
        verified = []
        for r, score in pre_selected:
            if r.image_url:
                match = compare_images(ebay_image_url, r.image_url)
                if match == "yes":
                    score += 15
                    logger.info(f"    画像一致: [{r.platform}] {r.title[:30]}")
                elif match == "no":
                    score -= 20
                    logger.info(f"    画像不一致: [{r.platform}] {r.title[:30]}")
            verified.append((r, score))
        verified.sort(key=lambda x: x[1], reverse=True)
        pre_selected = verified

    # 上位N件を返す
    selected = []
    for r, score in pre_selected[:top_n]:
        selected.append({
            "platform": r.platform,
            "title": r.title,
            "price_jpy": r.price_jpy,
            "shipping_jpy": getattr(r, 'shipping_jpy', 0),
            "total_price_jpy": r.price_jpy + getattr(r, 'shipping_jpy', 0),
            "condition": r.condition,
            "url": r.url,
            "image_url": r.image_url,
            "is_junk": r.is_junk,
            "score": round(score, 1),
        })

    logger.info(
        f"  → ベスト{len(selected)}件: "
        + " / ".join(f"[{c['platform']}] ¥{c['price_jpy']:,} ({c['score']}pt)" for c in selected)
    )

    return selected
