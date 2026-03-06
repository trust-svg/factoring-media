"""LINE占いリクエスト処理エージェント — 祈音（しおん）霊視鑑定"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import anthropic

from database.crud import (
    AsyncSessionLocal,
    get_or_create_user,
    get_total_reading_count,
)

STORES_URL = "https://sion-salon.stores.jp"

# 初回無料：通算1回を超えたら本鑑定へ誘導
FREE_READING_LIMIT = 1

UPSELL_MESSAGE = (
    "🔮 簡易鑑定はいかがでしたか？\n\n"
    "続きの深い部分（恋愛の転機・仕事の変化・\n"
    "具体的なタイミング）は本鑑定でお伝えします。\n\n"
    "気になった方はぜひ▼\n"
    f"▶ {STORES_URL}"
)

FORTUNE_SYSTEM_PROMPT = """あなたは「祈音（しおん）」という名前の霊視鑑定師です。
縁の声（えにしのこえ）を聴き、相談者の魂の状態や縁の流れを視る能力を持っています。

【あなたのスタイル】
- タロットカードや星座ではなく「霊視」で視えたものを伝える
- 「縁の声が〜と伝えています」「お二人の間に〜が視えます」という表現を使う
- 温かく、寄り添いながらも核心を突く言葉を選ぶ
- 相談者の名前が分かる場合は名前を呼びかける

【簡易鑑定のルール】
1. 相談者のメッセージ（悩み・質問内容）を丁寧に受け止める一言から始める
2. 霊視で視えたものとして、2〜3文で核心的な洞察を伝える
   - 相談内容に寄り添った具体的な内容にすること
   - 「〜が視えます」「縁の声が〜と伝えています」という表現
   - 断定ではなく「〜の気配があります」「〜を示しています」
3. 続きが気になる「引き」を作る
   - 「この先の流れについて、もう少し深く視えているものがあります...」
   - 「お相手の本心について、縁の声がまだ伝えたいことがあるようです...」
   - ※ 文章が途中で終わるように書くこと
4. 本鑑定への自然なCTA

【返答フォーマット】
🔮

[相談者への寄り添いの一言]

[霊視で視えた内容 2〜3文。最後の文は途中で終わらせる]

✨ この先のこと、もう少し深く視えているものがあります。
本鑑定でじっくりお伝えさせてください。
▶ sion-salon.stores.jp

【注意】
- タロット・星座・数秘術などのキーワードは使わない
- 医療・法律・投資アドバイスは含めない
- 「必ず〜になる」などの断定表現は避ける
- 絵文字は控えめに（1〜3個程度）
- 「AI」「人工知能」などの言葉は絶対に使わない
"""


@dataclass
class FortuneResult:
    reading_type: str
    draft_text: str
    limit_reached: bool


async def run_fortune_agent(line_user_id: str, user_message: str) -> FortuneResult:
    """
    祈音の霊視鑑定を生成し、FortuneResult を返す。
    DB保存は呼び出し元（main.py）で行う。
    """
    # 初回無料チェック（API呼び出し前に確認してコスト節約）
    async with AsyncSessionLocal() as session:
        await get_or_create_user(session, line_user_id)
        count = await get_total_reading_count(session, line_user_id)
        if count >= FREE_READING_LIMIT:
            return FortuneResult(
                reading_type="upsell",
                draft_text=UPSELL_MESSAGE,
                limit_reached=True,
            )

    client = anthropic.Anthropic()
    today = date.today().strftime("%Y年%m月%d日")

    system = (
        FORTUNE_SYSTEM_PROMPT
        + f"\n\n本日の日付: {today}\n"
        "相談者から届いたメッセージをもとに、霊視鑑定を行ってください。\n"
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )

    draft_text = " ".join(
        block.text for block in response.content if hasattr(block, "text")
    ).strip()

    return FortuneResult(
        reading_type="reishi",
        draft_text=draft_text,
        limit_reached=False,
    )
