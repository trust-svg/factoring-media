"""ZINQ Suite — プロフィール写真診断Bot

Claude Vision APIで写真を分析してスコアと改善ポイントを返す。
写真本体はこのモジュールの外に出さない（呼び出し元で即破棄）。
"""
from __future__ import annotations

import base64
import json
import logging

import anthropic

logger = logging.getLogger(__name__)

STANDARD_MONTHLY_LIMIT = 10

DIAGNOSIS_PROMPT = """あなたはマッチングアプリのプロフィール写真の専門家です。

この写真を、20〜35歳の日本人男性がマッチングアプリで使うプロフィール写真として評価してください。

以下のJSON形式のみで回答してください（他の文章は不要）:
{
  "score": <0.0〜10.0の数値、小数点1桁>,
  "points": [
    "<改善ポイント1（具体的な問題点と影響する推定点数を含む）>",
    "<改善ポイント2>",
    "<改善ポイント3>"
  ],
  "potential_score": <改善後の推定スコア、小数点1桁>
}

評価基準:
- 笑顔・表情の自然さ（重要度: 高）
- 背景の清潔感・シンプルさ（重要度: 高）
- 光の向き・顔の明るさ（重要度: 中）
- 服装・清潔感（重要度: 中）
- 構図・角度（重要度: 低）"""


async def diagnose_photo(
    image_data: bytes,
    image_media_type: str = "image/jpeg",
) -> tuple[float, list[str], float]:
    """写真を診断してスコア・改善ポイント3つ・改善後推定スコアを返す。

    Returns:
        (score, points, potential_score)
        写真本体はここで使用後、呼び出し元で破棄すること。
    """
    client = anthropic.AsyncAnthropic()
    image_b64 = base64.standard_b64encode(image_data).decode("utf-8")

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image_media_type,
                        "data": image_b64,
                    },
                },
                {"type": "text", "text": DIAGNOSIS_PROMPT},
            ],
        }],
    )

    result = json.loads(response.content[0].text)
    return float(result["score"]), list(result["points"]), float(result["potential_score"])


def format_diagnosis_result(
    score: float,
    points: list[str],
    potential_score: float,
    is_free: bool = True,
) -> str:
    """診断結果をLINEメッセージ用にフォーマットする"""
    lines = [
        "📊 プロフィール診断結果\n",
        f"スコア: {score:.1f} / 10\n",
        "改善ポイント:",
    ]
    for i, point in enumerate(points, 1):
        lines.append(f"{'①②③'[i-1]} {point}")

    lines.append(f"\n改善すれば {potential_score:.1f}点 まで上げられます。")

    if is_free:
        lines.extend([
            "",
            "━━━━━━━━━━━━━━",
            "✨ 各改善ポイントの具体的な対策、",
            "自己紹介文の改善もしたい方は",
            "→ Standardプランで続ける",
            "（¥980/月、全Bot月10回利用可）",
        ])

    return "\n".join(lines)


def check_usage_limit(plan: str, monthly_count: int) -> str | None:
    """利用制限チェック。制限超過の場合はアップセルメッセージを返す。Noneなら利用可能。"""
    if plan == "free":
        return (
            "無料診断は1回までです。\n\n"
            "続けて使うには→ Standardプラン（¥980/月）\n"
            "全Bot使い放題→ Premiumプラン（¥2,480/月）"
        )
    if plan == "standard" and monthly_count >= STANDARD_MONTHLY_LIMIT:
        return (
            f"今月のプロフィール診断（{STANDARD_MONTHLY_LIMIT}回）を使い切りました。\n\n"
            "使い放題にするには→ Premiumプラン（¥2,480/月）"
        )
    return None  # 利用可能
