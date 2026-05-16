"""
語彙ネットワーク: 語根ベースのクラスタリング済み英検頻出語彙
DB不要 — 静的データ。ユーザーがカードをデッキに追加する操作はflashcards APIへ。
"""

from fastapi import APIRouter, Depends

from app.deps import current_user
from app.models.user import User

router = APIRouter()

# 英検準2級・2級頻出語 — 語根クラスター
_CLUSTERS = [
    # ─── 準2級クラスター ────────────────────────────────────────────
    {
        "id": "pre2-act",
        "root": "act（行動する）",
        "grade": "pre2",
        "color": "#6366f1",
        "members": [
            {
                "word": "act",
                "pos": "v/n",
                "meaning": "行動する / 行為",
                "example": "She acts kindly.",
            },
            {
                "word": "action",
                "pos": "n",
                "meaning": "行動・行為",
                "example": "Take action now.",
            },
            {
                "word": "active",
                "pos": "adj",
                "meaning": "活動的な",
                "example": "He is very active.",
            },
            {
                "word": "activity",
                "pos": "n",
                "meaning": "活動・行事",
                "example": "Club activities are fun.",
            },
            {
                "word": "actor",
                "pos": "n",
                "meaning": "俳優",
                "example": "He is a famous actor.",
            },
            {
                "word": "react",
                "pos": "v",
                "meaning": "反応する",
                "example": "How did she react?",
            },
        ],
    },
    {
        "id": "pre2-care",
        "root": "care（気にかける）",
        "grade": "pre2",
        "color": "#22c55e",
        "members": [
            {
                "word": "care",
                "pos": "v/n",
                "meaning": "気にかける / 世話",
                "example": "I care about you.",
            },
            {
                "word": "careful",
                "pos": "adj",
                "meaning": "注意深い",
                "example": "Be careful!",
            },
            {
                "word": "careless",
                "pos": "adj",
                "meaning": "不注意な",
                "example": "Don't be careless.",
            },
            {
                "word": "carelessly",
                "pos": "adv",
                "meaning": "不注意に",
                "example": "He spoke carelessly.",
            },
            {
                "word": "caregiver",
                "pos": "n",
                "meaning": "介護者・世話人",
                "example": "She is a skilled caregiver.",
            },
        ],
    },
    {
        "id": "pre2-help",
        "root": "help（助ける）",
        "grade": "pre2",
        "color": "#f59e0b",
        "members": [
            {
                "word": "help",
                "pos": "v/n",
                "meaning": "助ける / 助け",
                "example": "Can you help me?",
            },
            {
                "word": "helpful",
                "pos": "adj",
                "meaning": "役に立つ",
                "example": "She is very helpful.",
            },
            {
                "word": "helpless",
                "pos": "adj",
                "meaning": "無力な",
                "example": "He felt helpless.",
            },
            {
                "word": "helper",
                "pos": "n",
                "meaning": "助ける人・手伝い",
                "example": "A good helper is needed.",
            },
        ],
    },
    {
        "id": "pre2-use",
        "root": "use（使う）",
        "grade": "pre2",
        "color": "#f43f5e",
        "members": [
            {
                "word": "use",
                "pos": "v/n",
                "meaning": "使う / 使用",
                "example": "Use a dictionary.",
            },
            {
                "word": "useful",
                "pos": "adj",
                "meaning": "役立つ",
                "example": "This map is useful.",
            },
            {
                "word": "useless",
                "pos": "adj",
                "meaning": "役に立たない",
                "example": "That excuse is useless.",
            },
            {
                "word": "user",
                "pos": "n",
                "meaning": "使用者・ユーザー",
                "example": "App users are increasing.",
            },
            {
                "word": "reuse",
                "pos": "v",
                "meaning": "再利用する",
                "example": "Reuse plastic bags.",
            },
        ],
    },
    {
        "id": "pre2-friend",
        "root": "friend（友人）",
        "grade": "pre2",
        "color": "#8b5cf6",
        "members": [
            {
                "word": "friend",
                "pos": "n",
                "meaning": "友人",
                "example": "She is my best friend.",
            },
            {
                "word": "friendly",
                "pos": "adj",
                "meaning": "親しみやすい",
                "example": "He is friendly to everyone.",
            },
            {
                "word": "unfriendly",
                "pos": "adj",
                "meaning": "不親切な",
                "example": "Why is she unfriendly?",
            },
            {
                "word": "friendship",
                "pos": "n",
                "meaning": "友情",
                "example": "Their friendship is strong.",
            },
            {
                "word": "befriend",
                "pos": "v",
                "meaning": "友達になる",
                "example": "He befriended a new student.",
            },
        ],
    },
    {
        "id": "pre2-danger",
        "root": "danger（危険）",
        "grade": "pre2",
        "color": "#ef4444",
        "members": [
            {
                "word": "danger",
                "pos": "n",
                "meaning": "危険",
                "example": "There is danger ahead.",
            },
            {
                "word": "dangerous",
                "pos": "adj",
                "meaning": "危険な",
                "example": "It is a dangerous road.",
            },
            {
                "word": "endanger",
                "pos": "v",
                "meaning": "危険にさらす",
                "example": "Pollution endangers wildlife.",
            },
            {
                "word": "endangered",
                "pos": "adj",
                "meaning": "絶滅危惧の",
                "example": "Pandas are endangered.",
            },
        ],
    },
    {
        "id": "pre2-health",
        "root": "health（健康）",
        "grade": "pre2",
        "color": "#10b981",
        "members": [
            {
                "word": "health",
                "pos": "n",
                "meaning": "健康",
                "example": "Good health is important.",
            },
            {
                "word": "healthy",
                "pos": "adj",
                "meaning": "健康的な",
                "example": "Eat healthy food.",
            },
            {
                "word": "unhealthy",
                "pos": "adj",
                "meaning": "不健康な",
                "example": "Junk food is unhealthy.",
            },
            {
                "word": "healthcare",
                "pos": "n",
                "meaning": "医療・保健",
                "example": "Healthcare costs are rising.",
            },
        ],
    },
    # ─── 2級クラスター ──────────────────────────────────────────────
    {
        "id": "2-port",
        "root": "port（運ぶ）",
        "grade": "2",
        "color": "#3b82f6",
        "members": [
            {
                "word": "import",
                "pos": "v/n",
                "meaning": "輸入する / 輸入品",
                "example": "Japan imports a lot of oil.",
            },
            {
                "word": "export",
                "pos": "v/n",
                "meaning": "輸出する / 輸出品",
                "example": "Cars are a major export.",
            },
            {
                "word": "transport",
                "pos": "v/n",
                "meaning": "輸送する / 輸送",
                "example": "We transport goods by ship.",
            },
            {
                "word": "portable",
                "pos": "adj",
                "meaning": "持ち運び可能な",
                "example": "A portable device is convenient.",
            },
            {
                "word": "support",
                "pos": "v/n",
                "meaning": "支える / 支援",
                "example": "Support your local community.",
            },
            {
                "word": "report",
                "pos": "v/n",
                "meaning": "報告する / 報告書",
                "example": "Please report the results.",
            },
        ],
    },
    {
        "id": "2-struct",
        "root": "struct（建てる・構造）",
        "grade": "2",
        "color": "#f97316",
        "members": [
            {
                "word": "structure",
                "pos": "n",
                "meaning": "構造・建造物",
                "example": "The structure is old.",
            },
            {
                "word": "construct",
                "pos": "v",
                "meaning": "建設する",
                "example": "They construct a new bridge.",
            },
            {
                "word": "construction",
                "pos": "n",
                "meaning": "建設・工事",
                "example": "Construction is underway.",
            },
            {
                "word": "instruct",
                "pos": "v",
                "meaning": "指示する・教える",
                "example": "The teacher instructs students.",
            },
            {
                "word": "instruction",
                "pos": "n",
                "meaning": "指示・説明書",
                "example": "Follow the instructions.",
            },
            {
                "word": "restructure",
                "pos": "v",
                "meaning": "再編する",
                "example": "The company will restructure.",
            },
        ],
    },
    {
        "id": "2-ject",
        "root": "ject（投げる）",
        "grade": "2",
        "color": "#ec4899",
        "members": [
            {
                "word": "project",
                "pos": "n/v",
                "meaning": "計画・プロジェクト / 投影する",
                "example": "Work on a school project.",
            },
            {
                "word": "object",
                "pos": "n/v",
                "meaning": "物・目的 / 反対する",
                "example": "She objects to the plan.",
            },
            {
                "word": "subject",
                "pos": "n",
                "meaning": "科目・主語・主題",
                "example": "English is my favorite subject.",
            },
            {
                "word": "reject",
                "pos": "v",
                "meaning": "拒否する・却下する",
                "example": "The proposal was rejected.",
            },
            {
                "word": "inject",
                "pos": "v",
                "meaning": "注射する・注入する",
                "example": "The doctor injected the medicine.",
            },
        ],
    },
    {
        "id": "2-scribe",
        "root": "scribe / script（書く）",
        "grade": "2",
        "color": "#06b6d4",
        "members": [
            {
                "word": "describe",
                "pos": "v",
                "meaning": "描写する・説明する",
                "example": "Describe the scene.",
            },
            {
                "word": "description",
                "pos": "n",
                "meaning": "描写・説明",
                "example": "Give a brief description.",
            },
            {
                "word": "prescribe",
                "pos": "v",
                "meaning": "処方する",
                "example": "The doctor prescribed medicine.",
            },
            {
                "word": "subscribe",
                "pos": "v",
                "meaning": "購読する・登録する",
                "example": "Subscribe to the newsletter.",
            },
            {
                "word": "subscription",
                "pos": "n",
                "meaning": "購読・サブスク",
                "example": "A monthly subscription fee.",
            },
            {
                "word": "manuscript",
                "pos": "n",
                "meaning": "原稿・写本",
                "example": "The manuscript was found.",
            },
        ],
    },
    {
        "id": "2-cede",
        "root": "cede / ceed（行く・譲る）",
        "grade": "2",
        "color": "#a855f7",
        "members": [
            {
                "word": "proceed",
                "pos": "v",
                "meaning": "進む・続ける",
                "example": "Proceed with caution.",
            },
            {
                "word": "succeed",
                "pos": "v",
                "meaning": "成功する・後を継ぐ",
                "example": "She succeeded in her goal.",
            },
            {
                "word": "success",
                "pos": "n",
                "meaning": "成功",
                "example": "Hard work leads to success.",
            },
            {
                "word": "exceed",
                "pos": "v",
                "meaning": "超える",
                "example": "Do not exceed the speed limit.",
            },
            {
                "word": "excess",
                "pos": "n/adj",
                "meaning": "過剰 / 余分な",
                "example": "Avoid excess salt.",
            },
            {
                "word": "access",
                "pos": "n/v",
                "meaning": "アクセス / 利用する",
                "example": "Access to the internet.",
            },
        ],
    },
    {
        "id": "2-environ",
        "root": "environment（環境）",
        "grade": "2",
        "color": "#16a34a",
        "members": [
            {
                "word": "environment",
                "pos": "n",
                "meaning": "環境",
                "example": "Protect the environment.",
            },
            {
                "word": "environmental",
                "pos": "adj",
                "meaning": "環境の",
                "example": "Environmental problems are serious.",
            },
            {
                "word": "environmentally",
                "pos": "adv",
                "meaning": "環境的に",
                "example": "Environmentally friendly products.",
            },
            {
                "word": "environmentalist",
                "pos": "n",
                "meaning": "環境保護活動家",
                "example": "She is an environmentalist.",
            },
        ],
    },
    {
        "id": "2-econ",
        "root": "economy（経済）",
        "grade": "2",
        "color": "#ca8a04",
        "members": [
            {
                "word": "economy",
                "pos": "n",
                "meaning": "経済",
                "example": "The economy is growing.",
            },
            {
                "word": "economic",
                "pos": "adj",
                "meaning": "経済の",
                "example": "Economic growth is important.",
            },
            {
                "word": "economical",
                "pos": "adj",
                "meaning": "経済的・節約できる",
                "example": "This car is economical.",
            },
            {
                "word": "economics",
                "pos": "n",
                "meaning": "経済学",
                "example": "He studies economics.",
            },
            {
                "word": "economist",
                "pos": "n",
                "meaning": "経済学者",
                "example": "Economists predict growth.",
            },
        ],
    },
    {
        "id": "2-tech",
        "root": "technology（技術）",
        "grade": "2",
        "color": "#0ea5e9",
        "members": [
            {
                "word": "technology",
                "pos": "n",
                "meaning": "技術・テクノロジー",
                "example": "New technology changes life.",
            },
            {
                "word": "technological",
                "pos": "adj",
                "meaning": "技術的な",
                "example": "Technological advances are rapid.",
            },
            {
                "word": "technique",
                "pos": "n",
                "meaning": "技法・テクニック",
                "example": "Learn the technique.",
            },
            {
                "word": "technical",
                "pos": "adj",
                "meaning": "技術的な・専門的な",
                "example": "Technical skills are needed.",
            },
            {
                "word": "technically",
                "pos": "adv",
                "meaning": "技術的に・厳密には",
                "example": "Technically, it is correct.",
            },
        ],
    },
]


@router.get("/clusters")
def get_clusters(
    grade: str | None = None,
    user: User = Depends(current_user),
):
    clusters = _CLUSTERS
    if grade:
        clusters = [c for c in clusters if c["grade"] == grade]
    return {"clusters": clusters, "total": len(clusters)}
