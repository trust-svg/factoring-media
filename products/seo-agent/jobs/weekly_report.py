from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

# allow `python jobs/weekly_report.py` and `python -m jobs.weekly_report`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db
from core.analyzer import affiliate_funnel_only, classify, split_by_tier
from core.gsc_client import fetch_window
from core.notifier import notify
from core.report import ReportContext, render, telegram_summary
from core.sites import Site
from sites import all_sites


def _select_sites(names: list[str] | None) -> list[Site]:
    sites = all_sites()
    if not names:
        return sites
    selected = [s for s in sites if s.name in names]
    missing = set(names) - {s.name for s in selected}
    if missing:
        raise SystemExit(f"unknown site(s): {missing}")
    return selected


def _process_site(site: Site, run_date: date, lookback_days: int, dry_run: bool) -> tuple[int, int, int, int, Path | None]:
    end_day = run_date - timedelta(days=3)  # GSC has ~2-3 day lag
    rows = fetch_window(site.gsc_property, end_day, lookback_days)

    iso = end_day.isoformat()
    if not dry_run:
        db.upsert_rows(site.name, iso, rows)

    def previous_lookup(keyword: str, page: str) -> float | None:
        if dry_run:
            return None
        return db.fetch_previous_position(site.name, keyword, page, iso)

    insights = classify(rows, previous_lookup=previous_lookup)
    buckets = split_by_tier(insights)
    affiliate = affiliate_funnel_only(insights)

    ctx = ReportContext(
        site=site,
        run_date=run_date.isoformat(),
        buckets=buckets,
        affiliate_funnel=affiliate,
    )
    md = render(ctx)

    reports_root = Path(os.getenv("REPORTS_DIR", "/app/reports"))
    target_dir = reports_root / ("dry-run" if dry_run else run_date.isoformat())
    target_dir.mkdir(parents=True, exist_ok=True)
    report_path = target_dir / f"{site.name}.md"
    report_path.write_text(md, encoding="utf-8")

    if not dry_run:
        db.record_run(site.name, run_date.isoformat(), len(rows), str(report_path))

    return (
        len(buckets.get("rewrite", [])),
        len(buckets.get("title", [])),
        len(buckets.get("seed", [])),
        len(affiliate),
        report_path,
    )


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="SEO weekly report")
    parser.add_argument("--site", action="append", help="restrict to site name (repeatable)")
    parser.add_argument("--dry-run", action="store_true", help="skip DB write and Telegram notify")
    parser.add_argument("--lookback-days", type=int, default=int(os.getenv("LOOKBACK_DAYS", "28")))
    args = parser.parse_args()

    if not args.dry_run:
        db.init_schema()

    sites = _select_sites(args.site)
    run_date = date.today()

    summary: list[tuple[str, int, int, int, int]] = []
    paths: list[Path] = []
    for site in sites:
        try:
            rw, ti, se, af, path = _process_site(site, run_date, args.lookback_days, args.dry_run)
            summary.append((site.name, rw, ti, se, af))
            if path:
                paths.append(path)
            print(f"[{site.name}] rewrite={rw} title={ti} seed={se} affiliate={af} -> {path}")
        except Exception as e:
            print(f"[{site.name}] ERROR: {e}", file=sys.stderr)
            if not args.dry_run:
                notify(f"❌ SEO週次レポート失敗: {site.name}\n{e}")

    if summary and not args.dry_run:
        notify(telegram_summary(summary, run_date.isoformat()))

    return 0 if summary else 1


if __name__ == "__main__":
    raise SystemExit(main())
