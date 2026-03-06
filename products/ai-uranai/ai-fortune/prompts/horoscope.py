"""星座占いプロンプト定義"""
from __future__ import annotations

ZODIAC_SIGNS: dict[str, str] = {
    "牡羊座": "3/21-4/19",
    "牡牛座": "4/20-5/20",
    "双子座": "5/21-6/20",
    "蟹座": "6/21-7/22",
    "獅子座": "7/23-8/22",
    "乙女座": "8/23-9/22",
    "天秤座": "9/23-10/22",
    "蠍座": "10/23-11/21",
    "射手座": "11/22-12/21",
    "山羊座": "12/22-1/19",
    "水瓶座": "1/20-2/18",
    "魚座": "2/19-3/20",
}

HOROSCOPE_SYSTEM_PROMPT = """あなたはプロの星座占い師です。
温かく、具体的で、前向きな星座鑑定を行います。

【鑑定スタイル】
- 恋愛・仕事・金運・健康の4項目にさりげなく触れる
- 今日のラッキーカラーまたはラッキーアイテムを1つ提案する
- 200〜250文字程度でまとめる
- 絵文字を適度に使って楽しく

【注意事項】
- 「必ず〜になります」などの断定表現は避ける
- 医療・投資アドバイスは含めない
- あくまでエンターテインメントとして楽しんでもらう
"""


def build_horoscope_prompt(sign: str, date_str: str) -> str:
    return f"星座: {sign}\n日付: {date_str}\n\n今日の運勢を鑑定してください。"


from typing import Optional

def detect_zodiac_from_text(text: str) -> Optional[str]:
    """テキストから星座名を検出する"""
    for sign in ZODIAC_SIGNS:
        if sign in text:
            return sign
    return None
