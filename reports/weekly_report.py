#!/usr/bin/env python3
"""
FACCEL 週次SEOレポート + Claude改善案
毎週月曜08:00にDiscord #マーケティング-ユウ-marketing に送信する
"""

import os
from datetime import date, timedelta
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from discord_notify import send_discord
from gsc_client import (
    get_opportunity_queries,
    get_service,
    get_summary,
    get_top_pages,
    get_top_queries,
)


def pct_change(current: float, previous: float) -> str:
    if previous == 0:
        return "+∞" if current > 0 else "±0"
    pct = (current - previous) / previous * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}%"


def position_change(current: float, previous: float) -> str:
    if previous == 0:
        return ""
    diff = previous - current  # 順位は小さい方が良いので逆
    if abs(diff) < 0.1:
        return "（変化なし）"
    arrow = "↑改善" if diff > 0 else "↓悪化"
    return f"（{arrow} {abs(diff):.1f}）"


def get_claude_suggestions(
    last_week: dict, top_queries: list, opportunities: list, top_pages: list
) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    queries_txt = "\n".join(
        f"- {q['query']} | クリック{q['clicks']} | 順位{q['position']:.0f}位"
        for q in top_queries[:5]
    )
    opps_txt = "\n".join(
        f"- {q['query']} | 表示{q['impressions']}回 | 順位{q['position']:.0f}位"
        for q in opportunities[:5]
    )
    pages_txt = "\n".join(
        f"- {p['page']} | クリック{p['clicks']} | 順位{p['position']:.0f}位"
        for p in top_pages[:5]
    )

    prompt = f"""FACCELはファクタリング（売掛金の早期現金化）の情報メディアです。SEOのみで集客し、ファクタリング業者へのアフィリエイトで収益を得ています。

【先週のSEO実績】
クリック: {last_week["clicks"]:,} / 表示: {last_week["impressions"]:,} / CTR: {last_week["ctr"] * 100:.1f}% / 平均順位: {last_week["position"]:.1f}位

【クリック上位クエリ（top5）】
{queries_txt}

【2ページ目チャンスクエリ（順位11-30、表示数多）】
{opps_txt}

【クリック上位ページ（top5）】
{pages_txt}

上記データをもとに、今週実行すべきSEO改善案を3〜5項目、優先度順に箇条書きで提案してください。具体的・実行可能な内容で、各項目は1〜2文で端的に。"""

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def main() -> None:
    today = date.today()
    end_last = today - timedelta(days=1)
    start_last = today - timedelta(days=7)
    end_prev = today - timedelta(days=8)
    start_prev = today - timedelta(days=14)

    service = get_service()

    last_week = get_summary(service, start_last.isoformat(), end_last.isoformat())
    prev_week = get_summary(service, start_prev.isoformat(), end_prev.isoformat())
    top_queries = get_top_queries(
        service, start_last.isoformat(), end_last.isoformat(), limit=10
    )
    top_pages = get_top_pages(
        service, start_last.isoformat(), end_last.isoformat(), limit=10
    )
    opportunities = get_opportunity_queries(
        service, start_last.isoformat(), end_last.isoformat()
    )

    suggestions = get_claude_suggestions(
        last_week, top_queries, opportunities, top_pages
    )

    period = f"{start_last.strftime('%m/%d')}〜{end_last.strftime('%m/%d')}"

    lines = [
        f"📊 **FACCEL 週次レポート** ({period})",
        "",
        "**🔍 SEOサマリー（前週比）**",
        f"  クリック:    {last_week['clicks']:,}（{pct_change(last_week['clicks'], prev_week['clicks'])}）",
        f"  表示回数:    {last_week['impressions']:,}（{pct_change(last_week['impressions'], prev_week['impressions'])}）",
        f"  平均CTR:     {last_week['ctr'] * 100:.1f}%（前週 {prev_week['ctr'] * 100:.1f}%）",
        f"  平均掲載順位: {last_week['position']:.1f}位{position_change(last_week['position'], prev_week['position'])}（前週 {prev_week['position']:.1f}位）",
        "",
        "**📄 クリック上位記事（top5）**",
    ]

    for i, p in enumerate(top_pages[:5], 1):
        slug = p["page"].strip("/").split("/")[-1] or "（トップ）"
        lines.append(
            f"  {i}. {slug} — {p['clicks']}クリック / 順位{p['position']:.0f}位"
        )

    if opportunities:
        lines += ["", "**🎯 2ページ目チャンス（順位11-30）**"]
        for q in opportunities[:5]:
            lines.append(
                f"  - {q['query']} — 順位{q['position']:.0f}位 / 表示{q['impressions']}回"
            )

    lines += ["", "**💡 今週の改善案（ユウ分析）**", suggestions]

    send_discord("\n".join(lines))
    print(f"Weekly report sent ({period}).")


if __name__ == "__main__":
    main()
