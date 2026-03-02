"""LINE占いリクエスト処理エージェント（Claude tool_use パターン）"""

import json
import random
from datetime import date
from typing import Any

import anthropic

from database.crud import (
    AsyncSessionLocal,
    get_or_create_user,
    get_total_reading_count,
    record_reading,
)
from prompts.horoscope import ZODIAC_SIGNS
from prompts.numerology import calculate_life_number, LIFE_NUMBER_MEANINGS

TAROT_CARDS: list[str] = [
    "愚者", "魔術師", "女教皇", "女帝", "皇帝", "法王",
    "恋人", "戦車", "力", "隠者", "運命の輪", "正義",
    "吊るされた男", "死神", "節制", "悪魔", "塔", "星",
    "月", "太陽", "審判", "世界",
]

STORES_URL = "https://sion-salon.stores.jp"

# 初回無料：通算1回を超えたら本鑑定へ誘導
FREE_READING_LIMIT = 1

UPSELL_MESSAGE = (
    "🔮 初回無料鑑定はいかがでしたか？\n\n"
    "続きの深い部分（恋愛の転機・仕事の変化・\n"
    "具体的なタイミング）は本鑑定でお伝えします。\n\n"
    "気になった方はぜひ▼\n"
    f"▶ {STORES_URL}"
)

# システムプロンプト：ティーザー形式（途中まで見せて本鑑定へ誘導）
FORTUNE_SYSTEM_PROMPT = """あなたはプロの占い師です。
ユーザーのメッセージに応じて占いのティーザー鑑定を行います。

【ティーザー鑑定のルール】
1. 最初の2〜3文で「当たっている」と感じさせる核心的な洞察を伝える
   - 具体的なキーワード（「変化」「待ちの時期」「新しい出会い」など）を使う
   - 断定ではなく「〜の気配があります」「〜を示しています」という表現を使う
2. 続きが気になる「引き」を作って文章を止める
   - 「この先には...」「特に注目すべきは...」「あなたの場合、重要なのは...」
   - ※ 文章が途中で終わるように書くこと
3. 本鑑定への自然なCTA（毎回必ず入れる）

【返答フォーマット】
🔮 [カード名 or 星座 or 運命数など]

[核心的な洞察 2〜3文。最後の文は途中で終わらせて読者を引き込む]

✨ この先（[具体的な内容例: 恋愛の転機・仕事の変化・タイミング]）は
本鑑定でじっくりお伝えします。
▶ sion-salon.stores.jp

【注意】
- 医療・法律・投資アドバイスは含めない
- 「必ず〜になる」などの断定表現は避ける
- 絵文字は控えめに（1〜3個程度）
"""

TOOLS: list[dict] = [
    {
        "name": "get_reading_count",
        "description": "ユーザーの通算鑑定回数を確認する（初回無料チェック用）",
        "input_schema": {
            "type": "object",
            "properties": {
                "line_user_id": {"type": "string"},
            },
            "required": ["line_user_id"],
        },
    },
    {
        "name": "draw_tarot_cards",
        "description": "タロットカードをランダムに引く",
        "input_schema": {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "引く枚数（1〜3）",
                    "minimum": 1,
                    "maximum": 3,
                },
            },
            "required": ["count"],
        },
    },
    {
        "name": "list_zodiac_signs",
        "description": "12星座のリストを取得する",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "calculate_life_number",
        "description": "生年月日から数秘術の運命数を計算する",
        "input_schema": {
            "type": "object",
            "properties": {
                "birthdate": {
                    "type": "string",
                    "description": "生年月日（YYYY-MM-DD 形式）",
                },
            },
            "required": ["birthdate"],
        },
    },
    {
        "name": "record_reading_result",
        "description": "鑑定結果をデータベースに保存する",
        "input_schema": {
            "type": "object",
            "properties": {
                "line_user_id": {"type": "string"},
                "reading_type": {
                    "type": "string",
                    "enum": ["tarot", "horoscope", "numerology", "daily"],
                },
                "result_text": {"type": "string"},
            },
            "required": ["line_user_id", "reading_type", "result_text"],
        },
    },
]


async def _execute_tool(name: str, tool_input: dict[str, Any]) -> str:
    if name == "get_reading_count":
        async with AsyncSessionLocal() as session:
            await get_or_create_user(session, tool_input["line_user_id"])
            count = await get_total_reading_count(session, tool_input["line_user_id"])
            return json.dumps(
                {
                    "total_count": count,
                    "free_limit": FREE_READING_LIMIT,
                    "limit_reached": count >= FREE_READING_LIMIT,
                }
            )

    elif name == "draw_tarot_cards":
        count = min(max(tool_input["count"], 1), 3)
        cards = [
            {"card": random.choice(TAROT_CARDS), "position": random.choice(["正位置", "逆位置"])}
            for _ in range(count)
        ]
        return json.dumps({"cards": cards})

    elif name == "list_zodiac_signs":
        return json.dumps({"signs": list(ZODIAC_SIGNS.keys())})

    elif name == "calculate_life_number":
        num = calculate_life_number(tool_input["birthdate"])
        meaning = LIFE_NUMBER_MEANINGS.get(num, "")
        return json.dumps({"life_number": num, "meaning": meaning})

    elif name == "record_reading_result":
        async with AsyncSessionLocal() as session:
            await record_reading(
                session,
                line_user_id=tool_input["line_user_id"],
                reading_type=tool_input["reading_type"],
                result_text=tool_input["result_text"],
            )
        return json.dumps({"status": "saved"})

    return json.dumps({"error": f"Unknown tool: {name}"})


async def run_fortune_agent(line_user_id: str, user_message: str) -> str:
    """
    FortuneAgent のエントリーポイント。
    ティーザー形式で鑑定し、本鑑定（STORES）へ誘導する。
    """
    # 初回無料チェック（API呼び出し前に確認してコスト節約）
    async with AsyncSessionLocal() as session:
        await get_or_create_user(session, line_user_id)
        count = await get_total_reading_count(session, line_user_id)
        if count >= FREE_READING_LIMIT:
            return UPSELL_MESSAGE

    client = anthropic.Anthropic()
    today = date.today().isoformat()

    system = (
        FORTUNE_SYSTEM_PROMPT
        + f"\n\n本日の日付: {today}\nユーザーID: {line_user_id}\n\n"
        "手順:\n"
        "1. get_today_count で本日の回数を確認（上限に達していたら上限メッセージを返す）\n"
        "2. 占い種別を判断して実行する（タロット → draw_tarot_cards を必ず使う）\n"
        "3. record_reading_result で結果を保存する\n"
        "4. ティーザーフォーマットで返答する\n"
    )

    messages: list[dict] = [{"role": "user", "content": user_message}]

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        system=system,
        tools=TOOLS,
        messages=messages,
    )

    # エージェントループ
    while response.stop_reason == "tool_use":
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = await _execute_tool(block.name, block.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

    return " ".join(
        block.text for block in response.content if hasattr(block, "text")
    ).strip()
