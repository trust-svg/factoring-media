"""仕入れ検索スクレイパー共通ユーティリティ

ebay-agent 内蔵スクレイパー用の共通定数・関数。
各スクレイパーは sourcing.schema.SourceCandidate を返す。
"""

import re

# ── 共通定数 ──

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.9",
}

# ジャンク品判定キーワード
JUNK_KEYWORDS = [
    "ジャンク", "junk", "現状品", "現状渡し", "動作未確認",
    "動作不良", "故障", "部品取り", "訳あり", "難あり",
    "as is", "for parts", "not working", "broken",
]


def is_junk(title: str, condition: str = "") -> bool:
    """タイトル・状態テキストからジャンク品か判定"""
    combined = (title + " " + condition).lower()
    return any(kw.lower() in combined for kw in JUNK_KEYWORDS)


def guess_condition(title: str, condition_text: str = "") -> str:
    """タイトル・状態テキストからコンディションを推定"""
    combined = (title + " " + condition_text).lower()

    _MAPPING = [
        ("ジャンク", "ジャンク"), ("junk", "ジャンク"),
        ("現状品", "現状品"), ("現状渡し", "現状品"),
        ("動作未確認", "動作未確認"), ("動作不良", "動作不良"),
        ("故障", "故障"), ("部品取り", "部品取り"),
        ("訳あり", "訳あり"), ("難あり", "難あり"), ("as is", "ジャンク"),
        ("やや傷や汚れあり", "やや傷あり"), ("傷や汚れあり", "傷あり"),
        ("傷あり", "傷あり"), ("使用感あり", "使用感あり"),
        ("動作確認済", "動作確認済"), ("動作品", "動作品"),
        ("動作良好", "動作良好"), ("完動品", "完動品"),
        ("新品未開封", "新品未開封"), ("未開封", "未開封"),
        ("新品同様", "新品同様"), ("未使用に近い", "未使用に近い"),
        ("未使用", "未使用"), ("新品", "新品"),
        ("極美品", "極美品"), ("超美品", "超美品"),
        ("美品", "美品"), ("良品", "良品"),
        ("目立った傷や汚れなし", "目立った傷なし"),
        ("中古", "中古品"),
    ]

    for keyword, label in _MAPPING:
        if keyword in combined:
            return label
    return "記載なし"


def parse_price(text: str) -> int:
    """価格テキストから数値を抽出"""
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else 0
