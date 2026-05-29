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


def send_daily_summary(
    username: str,
    streak: int,
    sessions: list[dict],
    flashcard_count: int = 0,
) -> None:
    if not _TOKEN or not _CHAT_ID:
        return

    skill_ja = {
        "reading": "リーディング",
        "listening": "リスニング",
        "writing": "ライティング",
        "speaking": "スピーキング",
    }

    lines = [
        f"📋 <b>今日の学習まとめ</b>\n━━━━━━━━━━━━\n👤 {username}  🔥 {streak}日連続\n"
    ]
    for s in sessions:
        emoji = SKILL_EMOJI.get(s["skill"], "📚")
        skill = skill_ja.get(s["skill"], s["skill"])
        minutes = s["duration"] // 60
        seconds = s["duration"] % 60
        duration_str = f"{minutes}分{seconds}秒" if minutes > 0 else f"{seconds}秒"
        accuracy = (
            f"{round(s['correct'] / s['attempted'] * 100)}%"
            if s["attempted"] > 0
            else "—"
        )
        lines.append(
            f"{emoji} {skill}\n"
            f"⏱ {duration_str}  📝 {s['attempted']}問 / 正答率 {accuracy}"
        )

    if flashcard_count > 0:
        lines.append(f"🃏 単語カード\n📝 {flashcard_count}枚復習")

    text = "\n\n".join(lines)

    try:
        httpx.post(
            _BASE,
            json={"chat_id": _CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=5,
        )
    except Exception:
        pass
