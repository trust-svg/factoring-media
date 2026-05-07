"""Format video-analyzer responses for Discord.

Splits a VideoAnalysis dict into three messages so each fits comfortably under
Discord's 2000-char limit, and provides a View with a 📄 全文 button that
fetches the transcript on demand.
"""

from __future__ import annotations

import base64
import io
import logging
from typing import Any

import discord

from tools import video_analyzer

logger = logging.getLogger(__name__)


def _platform_emoji(platform: str | None) -> str:
    return {
        "youtube": "🎬",
        "tiktok": "🎵",
        "instagram": "📸",
        "threads": "🧵",
        "x": "🐦",
        "facebook": "📘",
    }.get((platform or "other").lower(), "🎥")


def _truncate(text: str, limit: int) -> str:
    if not text:
        return ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def format_summary(analysis: dict[str, Any], row_id: int | None) -> str:
    """Message 1: title / hook / why_it_works / target / tone."""
    platform = analysis.get("platform") or "other"
    title = analysis.get("title") or "(タイトル不明)"
    uploader = analysis.get("uploader") or "?"
    duration = analysis.get("duration_sec")
    duration_str = f"{int(duration)}秒" if duration else "?"

    lines: list[str] = []
    lines.append(f"{_platform_emoji(platform)} **{_truncate(title, 200)}**")
    lines.append(f"投稿者: {uploader} / 再生時間: {duration_str} / row_id: `{row_id}`")
    lines.append("")
    lines.append(f"🪝 **フック**: {_truncate(analysis.get('hook') or '-', 400)}")
    lines.append("")
    lines.append(f"📝 **要約**: {_truncate(analysis.get('summary') or '-', 600)}")
    lines.append("")
    lines.append(
        f"💡 **なぜ効くか**: {_truncate(analysis.get('why_it_works') or '-', 500)}"
    )

    target = analysis.get("target_audience")
    tone = analysis.get("tone")
    if target or tone:
        lines.append("")
        lines.append(f"🎯 ターゲット: {target or '-'} / トーン: {tone or '-'}")

    return "\n".join(lines)


def format_structure_and_triggers(analysis: dict[str, Any]) -> str:
    """Message 2: structure blocks + triggers + CTA + keywords."""
    lines: list[str] = ["🧩 **構成**"]
    structure = analysis.get("structure") or []
    if structure:
        for b in structure[:8]:
            name = b.get("name", "?")
            start = b.get("start_sec", 0)
            end = b.get("end_sec", 0)
            summary = _truncate(b.get("summary") or "", 120)
            lines.append(f"- `{start:.0f}–{end:.0f}s` **{name}**: {summary}")
    else:
        lines.append("- (なし)")

    lines.append("")
    lines.append("🎣 **トリガー**")
    triggers = analysis.get("triggers") or []
    if triggers:
        for t in triggers[:6]:
            ttype = t.get("type", "?")
            why = _truncate(t.get("why_it_works") or "", 140)
            quote = t.get("quote")
            quote_part = f" — 「{_truncate(quote, 80)}」" if quote else ""
            lines.append(f"- **{ttype}**{quote_part}: {why}")
    else:
        lines.append("- (なし)")

    cta = analysis.get("cta")
    if cta and (cta.get("text") or cta.get("type")):
        lines.append("")
        placement = cta.get("placement_sec")
        placement_str = f"{placement:.0f}s時点 / " if placement else ""
        lines.append(
            f"📢 **CTA** ({placement_str}{cta.get('type') or '-'}): "
            f"{_truncate(cta.get('text') or '-', 200)}"
        )

    keywords = analysis.get("keywords") or []
    hashtags = analysis.get("hashtags") or []
    if keywords or hashtags:
        lines.append("")
        if keywords:
            lines.append(f"🔑 キーワード: {', '.join(keywords[:10])}")
        if hashtags:
            lines.append(
                f"🏷 ハッシュタグ: {' '.join('#' + h.lstrip('#') for h in hashtags[:10])}"
            )

    return _truncate("\n".join(lines), 1900)


async def fetch_keyframe_files(
    row_id: int, n: int = 3
) -> tuple[str, list[discord.File]]:
    """Fetch keyframes from video-analyzer and convert to discord.File attachments.

    Returns (caption_text, files). On error, files is empty and caption explains why.
    """
    try:
        data = await video_analyzer.get_keyframes(row_id, n=n)
    except Exception as e:
        logger.warning(f"keyframes fetch failed for row {row_id}: {e}")
        return (f"🖼 キーフレーム取得失敗: {e}", [])

    items = data.get("items") or []
    total = data.get("total_frames") or 0
    returned = data.get("returned") or 0

    files: list[discord.File] = []
    for item in items:
        try:
            raw = base64.b64decode(item.get("data_base64") or "")
            if not raw:
                continue
            fname = item.get("filename") or f"frame_{item.get('index', 0)}.jpg"
            files.append(discord.File(fp=io.BytesIO(raw), filename=fname))
        except Exception as e:
            logger.warning(f"keyframe decode failed: {e}")

    caption = f"🖼 **キーフレーム** ({returned}/{total} 枚抽出)"
    return (caption, files)


class VideoAnalysisView(discord.ui.View):
    """View attached to the analysis result with a 📄 全文 button.

    Clicking the button fetches /transcript from video-analyzer and posts it
    in-thread (as ephemeral if too long).
    """

    def __init__(self, row_id: int):
        super().__init__(timeout=None)
        self.row_id = row_id

    @discord.ui.button(
        label="📄 全文（書き起こし）", style=discord.ButtonStyle.secondary
    )
    async def show_transcript(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            data = await video_analyzer.get_transcript(self.row_id)
        except Exception as e:
            await interaction.followup.send(
                f"⚠️ 全文取得に失敗しました: {e}", ephemeral=True
            )
            return

        text = data.get("text") or "(空)"
        lang = data.get("language") or "?"
        segments = data.get("segments") or []

        # Send as a file if too long for a chat message
        if len(text) > 1800:
            buf = io.BytesIO(text.encode("utf-8"))
            await interaction.followup.send(
                f"📄 **全文書き起こし** (lang={lang}, {len(text)}文字, {len(segments)} セグメント)",
                file=discord.File(fp=buf, filename=f"transcript_{self.row_id}.txt"),
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"📄 **全文書き起こし** (lang={lang})\n```\n{text}\n```",
                ephemeral=True,
            )
