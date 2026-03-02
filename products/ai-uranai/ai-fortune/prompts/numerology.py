"""数秘術プロンプト定義"""

NUMEROLOGY_SYSTEM_PROMPT = """あなたは数秘術の専門家です。
生年月日から導き出された「運命数」をもとに、その人の本質と今のエネルギーを鑑定します。

【鑑定スタイル】
- 運命数の意味とその人の本質的な特徴を説明する
- 現在の状況に活かせる具体的なアドバイスを1〜2個含める
- 200〜250文字程度でまとめる
- 親しみやすい絵文字を適度に使う

【注意事項】
- 断定表現は避け「〜の傾向があります」「〜かもしれません」などを使う
- エンターテインメントとして楽しんでもらう
"""

LIFE_NUMBER_MEANINGS: dict[int, str] = {
    1: "リーダーシップと独立心",
    2: "協調性と直感力",
    3: "創造性と表現力",
    4: "安定と忍耐",
    5: "自由と変化",
    6: "愛情と責任感",
    7: "分析力と精神性",
    8: "実力と豊かさ",
    9: "博愛と完成",
    11: "直感と霊感（マスターナンバー）",
    22: "夢の実現者（マスターナンバー）",
    33: "奉仕と愛（マスターナンバー）",
}


def calculate_life_number(birthdate: str) -> int:
    """生年月日（YYYY-MM-DD または YYYYMMDD）から運命数を計算する"""
    digits = [int(d) for d in birthdate if d.isdigit()]
    total = sum(digits)
    while total >= 10 and total not in (11, 22, 33):
        total = sum(int(d) for d in str(total))
    return total


def build_numerology_prompt(birthdate: str) -> str:
    life_number = calculate_life_number(birthdate)
    meaning = LIFE_NUMBER_MEANINGS.get(life_number, "")
    return (
        f"生年月日: {birthdate}\n"
        f"運命数: {life_number}（{meaning}）\n\n"
        "この方の数秘術鑑定をしてください。"
    )
