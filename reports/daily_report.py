#!/usr/bin/env python3
"""
FACCEL 日次SEOレポート
毎朝07:00にGSCの昨日データをTelegramに送信する
"""

import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from gsc_client import get_service, get_summary, get_top_pages, query_gsc
from telegram_notify import send_telegram


def fmt_change(current: float, previous: float, higher_is_better: bool = True) -> str:
    if previous == 0:
        return ""
    diff = current - previous
    if abs(diff) < 0.01:
        return " (±0)"
    if higher_is_better:
        arrow = "↑" if diff > 0 else "↓"
    else:
        arrow = "↑" if diff < 0 else "↓"  # position: lower number = better
    return f" ({arrow}{abs(diff):.0f})"


def main() -> None:
    today = date.today()
    yesterday = today - timedelta(days=1)
    day_before = today - timedelta(days=2)

    service = get_service()

    yesterday_data = get_summary(service, yesterday.isoformat(), yesterday.isoformat())
    prev_data = get_summary(service, day_before.isoformat(), day_before.isoformat())
    top_pages = get_top_pages(
        service, yesterday.isoformat(), yesterday.isoformat(), limit=5
    )

    clicks = yesterday_data["clicks"]
    impressions = yesterday_data["impressions"]
    ctr = yesterday_data["ctr"] * 100
    position = yesterday_data["position"]

    lines = [
        f"📊 <b>FACCEL 日次レポート（{yesterday.strftime('%m/%d')}）</b>",
        "",
        "🔍 <b>オーガニック流入</b>",
        f"  クリック:    {clicks:,}{fmt_change(clicks, prev_data['clicks'])}",
        f"  表示回数:    {impressions:,}{fmt_change(impressions, prev_data['impressions'])}",
        f"  平均CTR:     {ctr:.1f}%",
        f"  平均掲載順位: {position:.1f}位{fmt_change(position, prev_data['position'], higher_is_better=False)}",
    ]

    if top_pages:
        lines += ["", "📄 <b>クリック上位記事</b>"]
        for i, p in enumerate(top_pages, 1):
            slug = p["page"].strip("/").split("/")[-1] or "（トップ）"
            lines.append(
                f"  {i}. {slug} — {p['clicks']}クリック / 順位{p['position']:.0f}位"
            )

    send_telegram("\n".join(lines))
    print(f"Daily report sent ({yesterday.isoformat()}).")


if __name__ == "__main__":
    main()
