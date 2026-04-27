from __future__ import annotations

from dataclasses import dataclass

from core.analyzer import KeywordInsight
from core.sites import Site


CATEGORY_LABEL = {
    "declining": "🔴 下落警告",
    "stagnant": "🟡 停滞",
    "rising": "🟢 上昇候補",
}

CATEGORY_ACTION = {
    "declining": "競合確認 + リライト最優先",
    "stagnant": "内部リンク・FAQ追加で押し上げ",
    "rising": "強化リライトで1ページ目押し込み",
}


@dataclass
class ReportContext:
    site: Site
    run_date: str
    buckets: dict[str, list[KeywordInsight]]


def _fmt_pos(p: float | None) -> str:
    return f"{p:.1f}" if p is not None else "—"


def _fmt_delta(d: float | None) -> str:
    if d is None:
        return "—"
    sign = "▼" if d > 0 else "▲" if d < 0 else "→"
    return f"{sign}{abs(d):.1f}"


def _section(label: str, items: list[KeywordInsight], action: str, site_url_match) -> str:
    if not items:
        return f"## {label} (0件)\n\nなし。\n"
    lines = [f"## {label} ({len(items)}件)", "", f"**推奨アクション**: {action}", ""]
    lines.append("| KW | URL | 先週順位 | 今週順位 | Δ | imp | clicks | CTR |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for it in items:
        article = site_url_match(it.page)
        url_label = article.title[:40] + "…" if article and len(article.title) > 40 else (article.title if article else it.page)
        lines.append(
            f"| {it.keyword} | [{url_label}]({it.page}) | {_fmt_pos(it.previous_position)} | "
            f"{it.position:.1f} | {_fmt_delta(it.delta)} | {it.impressions} | {it.clicks} | {it.ctr * 100:.2f}% |"
        )
    lines.append("")
    return "\n".join(lines)


def render(ctx: ReportContext) -> str:
    site = ctx.site
    declining = ctx.buckets.get("declining", [])
    stagnant = ctx.buckets.get("stagnant", [])
    rising = ctx.buckets.get("rising", [])

    header = [
        f"# {site.name} SEO週次レポート ({ctx.run_date})",
        "",
        f"- ドメイン: {site.domain}",
        f"- GSC プロパティ: `{site.gsc_property}`",
        f"- 抽出件数: 🔴 {len(declining)} / 🟡 {len(stagnant)} / 🟢 {len(rising)}",
        "",
    ]

    body = [
        _section(CATEGORY_LABEL["declining"], declining, CATEGORY_ACTION["declining"], site.find_article_by_url),
        _section(CATEGORY_LABEL["stagnant"], stagnant, CATEGORY_ACTION["stagnant"], site.find_article_by_url),
        _section(CATEGORY_LABEL["rising"], rising, CATEGORY_ACTION["rising"], site.find_article_by_url),
    ]

    footer = [
        "## Claude Code 推奨アクション",
        "",
        "1. 🔴 下落警告 を最優先でリライト依頼",
        "2. 🟡 停滞 は FAQ・内部リンク追加で押し上げ",
        "3. 🟢 上昇候補 は本文強化で1ページ目押し込み",
        "",
        "```",
        f"claude → @reports/{ctx.run_date}/{site.name}.md を読んで、リライト指示書を作って",
        "```",
        "",
    ]

    return "\n".join(header + body + footer)


def telegram_summary(reports: list[tuple[str, int, int, int]], run_date: str) -> str:
    """reports: list of (site_name, declining, stagnant, rising)"""
    lines = [f"<b>SEO週次レポート {run_date}</b>", ""]
    total = 0
    for name, d, s, r in reports:
        total += d + s + r
        lines.append(f"<b>{name}</b>: 🔴{d} / 🟡{s} / 🟢{r}")
    lines.append("")
    lines.append(f"レポート: <code>reports/{run_date}/</code>")
    lines.append("Mac側でClaude Codeに食わせてリライト依頼してください。")
    return "\n".join(lines)
