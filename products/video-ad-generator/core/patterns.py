"""ABパターン5種のプロンプト定義。
50代向けマッチングアプリ広告用の日本人女性キャラクター生成。
"""
from __future__ import annotations
import random

# ブロックワード: 実在人物参照を防ぐ著名人名など
_BLOCK_WORDS = [
    "aragaki", "yui", "ishihara", "satomi", "ayase", "haruka",
    "toda", "erika", "kitagawa", "keiko", "takeuchi", "yuuko",
    "綾瀬", "新垣", "石原", "戸田", "北川", "竹内",
    "real person", "celebrity", "idol", "actress", "actor",
]

PATTERNS: dict[str, dict] = {
    "A": {
        "theme": "ロマンティック系",
        "image_prompt": (
            "Portrait photo of a warm Japanese woman in her late 30s to early 40s, "
            "soft natural makeup, gentle smile, casual-elegant blouse in muted rose tones, "
            "sitting at a cozy cafe by a rain-streaked window, soft bokeh background, "
            "natural window light, upper body shot, realistic photography, no text, "
            "not a real person, fictional character"
        ),
        "video_prompt": (
            "The woman gently wraps her hands around a coffee cup and looks out at the rain, "
            "soft smile, slow cinematic camera pull-back, warm cafe ambience, "
            "peaceful romantic atmosphere"
        ),
    },
    "B": {
        "theme": "楽しさ系",
        "image_prompt": (
            "Portrait photo of a cheerful Japanese woman in her early 40s, "
            "natural makeup, bright genuine laugh, casual colorful outfit, "
            "sitting on a park bench surrounded by greenery and sunlight, "
            "upper body shot, realistic photography, no text, "
            "not a real person, fictional character"
        ),
        "video_prompt": (
            "The woman laughs lightly and brushes hair from her face, "
            "light breeze moves through the trees behind her, "
            "joyful energy, slow-motion capture, warm golden hour lighting"
        ),
    },
    "C": {
        "theme": "信頼感系",
        "image_prompt": (
            "Portrait photo of a composed Japanese woman in her mid 40s, "
            "minimal elegant makeup, calm confident expression, "
            "smart casual blazer in navy or grey, modern office environment background, "
            "upper body shot, realistic photography, no text, "
            "not a real person, fictional character"
        ),
        "video_prompt": (
            "The woman looks up from her desk and gives a small warm smile, "
            "calm and composed movement, soft office lighting, "
            "steady camera, professional yet approachable atmosphere"
        ),
    },
    "D": {
        "theme": "ユーモア系",
        "image_prompt": (
            "Portrait photo of a fun playful Japanese woman in her late 30s, "
            "light natural makeup, mischievous grin, casual trendy outfit, "
            "stylish modern cafe background with colorful decor, "
            "upper body shot, realistic photography, no text, "
            "not a real person, fictional character"
        ),
        "video_prompt": (
            "The woman notices the camera, breaks into a wide grin and gives a small wave, "
            "spontaneous and lighthearted movement, bright cafe atmosphere, "
            "handheld-style camera feel"
        ),
    },
    "E": {
        "theme": "真面目系",
        "image_prompt": (
            "Portrait photo of an intellectual Japanese woman in her early 50s, "
            "elegant minimal makeup, thoughtful expression, "
            "simple sophisticated blouse, library or bookshelf background, "
            "soft reading lamp light, upper body shot, realistic photography, no text, "
            "not a real person, fictional character"
        ),
        "video_prompt": (
            "The woman closes a book gently and looks up with a quiet confident smile, "
            "deliberate graceful movement, warm library lighting, "
            "slow zoom-in, intelligent serene atmosphere"
        ),
    },
}


def is_blocked(prompt: str) -> bool:
    """プロンプトに実在人物の名前や不適切なワードが含まれていないか確認。"""
    lower = prompt.lower()
    return any(word in lower for word in _BLOCK_WORDS)


def get_batch_prompts() -> list[dict]:
    """月バッチ用: 各パターン2本ずつ計10本のプロンプトリストを返す。"""
    batch = []
    for pattern_key, pattern in PATTERNS.items():
        for _ in range(2):
            batch.append({
                "pattern": pattern_key,
                "theme": pattern["theme"],
                "image_prompt": pattern["image_prompt"],
                "video_prompt": pattern["video_prompt"],
            })
    random.shuffle(batch)
    return batch
