import os
import httpx

_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
_BASE = f"https://api.telegram.org/bot{_TOKEN}/sendMessage"

SKILL_EMOJI = {
    "reading": "📖",
    "listening": "🎧",
    "writing": "✍️",
    "speaking": "🎤",
}


def send_session_summary(
    username: str,
    skill: str,
    duration_seconds: int,
    questions_attempted: int,
    correct_count: int,
    streak: int,
) -> None:
    if not _TOKEN or not _CHAT_ID:
        return

    emoji = SKILL_EMOJI.get(skill, "📚")
    skill_ja = {
        "reading": "リーディング",
        "listening": "リスニング",
        "writing": "ライティング",
        "speaking": "スピーキング",
    }.get(skill, skill)

    minutes = duration_seconds // 60
    seconds = duration_seconds % 60
    duration_str = f"{minutes}分{seconds}秒" if minutes > 0 else f"{seconds}秒"

    accuracy = (
        f"{round(correct_count / questions_attempted * 100)}%"
        if questions_attempted > 0
        else "—"
    )

    text = (
        f"{emoji} <b>学習セッション完了</b>\n"
        f"━━━━━━━━━━━━\n"
        f"👤 {username}\n"
        f"📚 {skill_ja}\n"
        f"⏱ {duration_str}\n"
        f"📝 {questions_attempted}問 / 正答率 {accuracy}\n"
        f"🔥 {streak}日連続"
    )

    try:
        httpx.post(
            _BASE,
            json={"chat_id": _CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=5,
        )
    except Exception:
        pass
