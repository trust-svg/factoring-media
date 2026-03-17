"""仕入候補スコアリング＆フィルタリング

仕入れ検索の3原則を反映したスコアリング:
  1. 巡回先を絞る → site_registry で管理（このファイルでは reliability を参照）
  2. 読む情報を絞る → schema.py の SourceCandidate のみ使用
  3. 画像判別を入れる → 画像比較をデフォルトON、スコア配分 30pt

スコア配分（0〜100pt）:
  - 価格スコア:      0〜30pt（上限価格との比較）
  - コンディション:  0〜25pt（新品→美品→動作確認済→ジャンク）
  - タイトル関連度:  0〜15pt（キーワード一致率）
  - 画像一致度:      0〜30pt（Claude Vision 判定）★ 最重要
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
    "case only", "ケースのみ",
    "adapter only", "アダプターのみ",
]

# 売り切れキーワード
SOLD_OUT_KEYWORDS = [
    "sold", "売り切れ", "販売終了", "取引終了",
]

# ── スコア配分定数 ──
SCORE_PRICE_MAX = 30        # 価格スコア上限
SCORE_CONDITION_MAX = 25    # コンディションスコア上限
SCORE_RELEVANCE_MAX = 15    # タイトル関連度上限
SCORE_IMAGE_MAX = 30        # 画像一致度上限 ★

# 画像比較なし候補のスコアキャップ（画像比較できない場合の最大スコア）
SCORE_CAP_NO_IMAGE = 70


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


def _score_price(total_jpy: int, max_price_jpy: int) -> float:
    """価格スコア (0〜30pt)"""
    if max_price_jpy <= 0 or total_jpy <= 0:
        return 0
    price_ratio = total_jpy / max_price_jpy
    return max(0, SCORE_PRICE_MAX * (1 - price_ratio))


def _score_condition(condition: str) -> float:
    """コンディションスコア (0〜25pt)"""
    raw = CONDITION_SCORES.get(condition, 15)
    return raw / 100 * SCORE_CONDITION_MAX


def _score_relevance(title: str, keyword: str) -> float:
    """タイトル関連度スコア (0〜15pt)"""
    kw_words = [w.lower() for w in keyword.split() if len(w) >= 2]
    if not kw_words:
        return 0
    title_lower = title.lower()
    match_count = sum(1 for w in kw_words if w in title_lower)
    return (match_count / len(kw_words)) * SCORE_RELEVANCE_MAX


def _score_image(ebay_image_url: str, candidate_image_url: str) -> tuple[float, str]:
    """画像一致度スコア (0〜30pt) + 判定結果

    Returns:
        (score, result) — result は "yes" | "maybe" | "no" | "skip" | "no_image"
    """
    if not ebay_image_url:
        # eBay側の画像がない場合はスキップ（ペナルティなし）
        return 0, "skip"

    if not candidate_image_url:
        # 候補側に画像がない → 判定不能
        return 0, "no_image"

    result = compare_images(ebay_image_url, candidate_image_url)

    if result == "yes":
        return SCORE_IMAGE_MAX, "yes"        # 30pt — 同一商品
    elif result == "maybe":
        return SCORE_IMAGE_MAX * 0.4, "maybe"  # 12pt — 類似
    elif result == "no":
        return -10, "no"                      # -10pt — 別商品ペナルティ
    else:
        return 0, "skip"                      # 0pt — API失敗


def pick_best_candidates(
    results: list,
    keyword: str,
    max_price_jpy: int,
    ebay_image_url: str = "",
    top_n: int = 5,
    site_reliability: dict[str, float] | None = None,
) -> list[dict]:
    """
    仕入候補をスコアリング・フィルタリングし、上位N件を返す。

    Args:
        results: スクレイパーからの候補リスト
        keyword: 検索キーワード
        max_price_jpy: 価格上限（円）
        ebay_image_url: eBay出品画像URL（画像比較用）★ 推奨
        top_n: 返す候補数
        site_reliability: サイトIDと信頼度のマッピング（site_registry から取得）

    Returns:
        スコア付き候補リスト（スコア内訳付き）
    """
    if not results:
        return []

    site_reliability = site_reliability or {}

    # ── フィルタリング ──

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

    # ── スコアリング（画像比較なし段階） ──
    scored = []
    for r in results:
        total = r.price_jpy + (r.shipping_jpy if hasattr(r, 'shipping_jpy') else 0)
        p_score = _score_price(total, max_price_jpy)
        c_score = _score_condition(r.condition)
        r_score = _score_relevance(r.title, keyword)

        # サイト信頼度ボーナス（0〜5pt）
        reliability = site_reliability.get(r.platform, 0.7)
        rel_bonus = reliability * 5  # 0.85 → 4.25pt

        base_score = p_score + c_score + r_score + rel_bonus
        scored.append({
            "result": r,
            "price_score": p_score,
            "condition_score": c_score,
            "relevance_score": r_score,
            "reliability_bonus": rel_bonus,
            "image_score": 0.0,
            "image_result": "pending",
            "total_score": base_score,
        })

    scored.sort(key=lambda x: x["total_score"], reverse=True)

    # プラットフォーム多様性: 同一プラットフォームは最大2件まで
    pre_selected = []
    platform_count: dict[str, int] = {}
    for item in scored:
        pf = item["result"].platform
        if platform_count.get(pf, 0) >= 2:
            continue
        pre_selected.append(item)
        platform_count[pf] = platform_count.get(pf, 0) + 1
        if len(pre_selected) >= top_n * 2:
            break

    # ── AI画像比較（デフォルトON） ──
    image_compared = False
    if ebay_image_url and pre_selected:
        image_compared = True
        for item in pre_selected:
            r = item["result"]
            if r.image_url:
                img_score, img_result = _score_image(ebay_image_url, r.image_url)
                item["image_score"] = img_score
                item["image_result"] = img_result
                item["total_score"] += img_score

                if img_result == "yes":
                    logger.info(f"    画像一致 (+{SCORE_IMAGE_MAX}pt): [{r.platform}] {r.title[:30]}")
                elif img_result == "no":
                    logger.info(f"    画像不一致 (-10pt): [{r.platform}] {r.title[:30]}")
                elif img_result == "maybe":
                    logger.info(f"    画像類似 (+{SCORE_IMAGE_MAX * 0.4:.0f}pt): [{r.platform}] {r.title[:30]}")
            else:
                item["image_result"] = "no_image"

        # 画像比較後のスコアキャップ: 画像がない候補は最大70ptに制限
        for item in pre_selected:
            if item["image_result"] in ("no_image", "skip"):
                item["total_score"] = min(item["total_score"], SCORE_CAP_NO_IMAGE)

        # 再ソート
        pre_selected.sort(key=lambda x: x["total_score"], reverse=True)

    elif not ebay_image_url:
        # eBay画像URLなし → 画像比較スキップ（警告を出す）
        logger.warning("  ⚠ ebay_image_url 未指定: 画像比較スキップ（精度が低下します）")

    # ── 結果組み立て ──
    selected = []
    for item in pre_selected[:top_n]:
        r = item["result"]
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
            "score": round(item["total_score"], 1),
            "score_breakdown": {
                "price": round(item["price_score"], 1),
                "condition": round(item["condition_score"], 1),
                "relevance": round(item["relevance_score"], 1),
                "image_match": round(item["image_score"], 1),
                "image_match_result": item["image_result"],
                "reliability_bonus": round(item["reliability_bonus"], 1),
            },
            "image_verified": item["image_result"] == "yes",
        })

    logger.info(
        f"  → ベスト{len(selected)}件 (画像比較: {'実施' if image_compared else '未実施'}): "
        + " / ".join(
            f"[{c['platform']}] ¥{c['price_jpy']:,} ({c['score']}pt"
            + (f", 画像:{c['score_breakdown']['image_match_result']}" if image_compared else "")
            + ")"
            for c in selected
        )
    )

    return selected
