from __future__ import annotations

from dataclasses import dataclass

from core.analyzer import KeywordInsight
from core.sites import Site


TIER_LABEL = {
    "rewrite": "🎯 即リライト (5〜30位)",
    "title": "📝 タイトル/構造改善 (30〜60位)",
    "seed": "🌱 種まき期 (60〜100位)",
}

TIER_ACTION = {
    "rewrite": "本文強化・FAQ追加・内部リンクで1ページ目押し込み",
    "title": "title / H1 / description 最適化でCTRと関連性スコア改善",
    "seed": "被リンク・内部リンク網・E-E-A-T 強化（記事単独より構造で攻める）",
}

TREND_MARK = {
    "declining": "▼",
    "stagnant": "→",
    "rising": "▲",
}


@dataclass
class ReportContext:
    site: Site
    run_date: str
    buckets: dict[str, list[KeywordInsight]]
    affiliate_funnel: list[KeywordInsight]


def _fmt_pos(p: float | None) -> str:
    return f"{p:.1f}" if p is not None else "—"


def _fmt_delta(d: float | None) -> str:
    if d is None:
        return "—"
    sign = "▼" if d > 0 else "▲" if d < 0 else "→"
    return f"{sign}{abs(d):.1f}"


def _row(it: KeywordInsight, site_url_match) -> str:
    article = site_url_match(it.page)
    if article:
        title = article.title
        url_label = title[:40] + "…" if len(title) > 40 else title
    else:
        url_label = it.page
    flags = []
    if it.ctr_zero_warning:
        flags.append("⚠️CTR0")
    if it.is_affiliate_funnel:
        flags.append("🛒")
    flag_str = " " + " ".join(flags) if flags else ""
    return (
        f"| {it.keyword}{flag_str} | [{url_label}]({it.page}) | "
        f"{_fmt_pos(it.previous_position)} | {it.position:.1f} | {_fmt_delta(it.delta)} | "
        f"{it.impressions} | {it.clicks} | {it.ctr * 100:.2f}% |"
    )


def _section(label: str, items: list[KeywordInsight], action: str, site_url_match) -> str:
    if not items:
        return f"## {label} (0件)\n\nなし。\n"
    lines = [f"## {label} ({len(items)}件)", "", f"**推奨アクション**: {action}", ""]
    lines.append("| KW | URL | 先週順位 | 今週順位 | Δ | imp | clicks | CTR |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for it in items:
        lines.append(_row(it, site_url_match))
    lines.append("")
    return "\n".join(lines)


def _affiliate_section(items: list[KeywordInsight], site_url_match) -> str:
    if not items:
        return ""
    lines = [
        f"## 🛒 アフィリ送客クエリ ({len(items)}件)",
        "",
        "**推奨アクション**: 直接収益に繋がる導線。CTR/CV最適化を最優先で確認",
        "",
        "| KW | URL | 先週順位 | 今週順位 | Δ | imp | clicks | CTR |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for it in items:
        lines.append(_row(it, site_url_match))
    lines.append("")
    return "\n".join(lines)


def render(ctx: ReportContext) -> str:
    site = ctx.site
    rewrite = ctx.buckets.get("rewrite", [])
    title = ctx.buckets.get("title", [])
    seed = ctx.buckets.get("seed", [])
    affiliate = ctx.affiliate_funnel

    header = [
        f"# {site.name} SEO週次レポート ({ctx.run_date})",
        "",
        f"- ドメイン: {site.domain}",
        f"- GSC プロパティ: `{site.gsc_property}`",
        f"- 抽出件数: 🎯 {len(rewrite)} / 📝 {len(title)} / 🌱 {len(seed)}（うち🛒アフィリ {len(affiliate)}）",
        "",
        "凡例: ▼順位悪化 / ▲順位改善 / →変化なし · ⚠️CTR0=表示あるがクリック0 · 🛒=アフィリ送客導線",
        "",
    ]

    body = [
        _section(TIER_LABEL["rewrite"], rewrite, TIER_ACTION["rewrite"], site.find_article_by_url),
        _section(TIER_LABEL["title"], title, TIER_ACTION["title"], site.find_article_by_url),
        _section(TIER_LABEL["seed"], seed, TIER_ACTION["seed"], site.find_article_by_url),
    ]

    affiliate_md = _affiliate_section(affiliate, site.find_article_by_url)
    if affiliate_md:
        body.append(affiliate_md)

    footer = [
        "## Claude Code 推奨アクション",
        "",
        "1. 🎯 **即リライト**：本文強化・FAQ・内部リンクで1ページ目（10位以内）に押し込む",
        "2. 📝 **タイトル/構造改善**：title / H1 / description を検索意図に合わせて最適化",
        "3. 🌱 **種まき期**：単記事リライトより、被リンク・内部リンク網・カテゴリ構造で底上げ",
        "4. 🛒 **アフィリ送客**：CV直結なのでCTRと回遊導線の検証を最優先",
        "5. ⚠️ **CTR0警告**：表示あるのにクリック0 → タイトル/メタディスクリプションが検索意図とズレている可能性",
        "",
        "```",
        f"claude → @reports/{ctx.run_date}/{site.name}.md を読んで、リライト指示書を作って",
        "```",
        "",
    ]

    return "\n".join(header + body + footer)


def telegram_summary(reports: list[tuple[str, int, int, int, int]], run_date: str) -> str:
    """reports: list of (site_name, rewrite, title, seed, affiliate)"""
    lines = [f"<b>SEO週次レポート {run_date}</b>", ""]
    total = 0
    for name, rw, ti, se, af in reports:
        total += rw + ti + se
        lines.append(f"<b>{name}</b>: 🎯{rw} / 📝{ti} / 🌱{se}（🛒{af}）")
    lines.append("")
    lines.append(f"レポート: <code>reports/{run_date}/</code>")
    lines.append("Mac側でClaude Codeに食わせてリライト依頼してください。")
    return "\n".join(lines)
