import os
from apscheduler.schedulers.background import BackgroundScheduler
import market
import trader
import db
import notify


def _jp_cycle() -> None:
    if market.is_jp_market_open():
        trader.run_trading_cycle("JP")


def _us_cycle() -> None:
    if market.is_us_market_open():
        trader.run_trading_cycle("US")


def _weekly_report() -> None:
    """毎週月曜 8:00 JST に週次パフォーマンスレポートをTelegramへ送信。"""
    portfolio = db.get_portfolio()
    positions = db.get_positions()
    usdjpy = market.get_usdjpy()
    prices = market.get_market_data([p["ticker"] for p in positions]) if positions else {}
    position_value = sum(
        prices.get(p["ticker"], p["avg_cost"]) * p["shares"] for p in positions
    )
    total = portfolio["cash_jp"] + portfolio["cash_us"] + position_value
    initial = float(os.getenv("INITIAL_CAPITAL", 10000))
    pnl = total - initial

    week_trades = db.get_trades_since(days=7)
    week_buys = sum(1 for t in week_trades if t["action"] == "BUY")
    week_sells = sum(1 for t in week_trades if t["action"] == "SELL")

    notify.notify_weekly_report(
        total_value=total,
        pnl=pnl,
        pnl_pct=(pnl / initial) * 100,
        cash_jp=portfolio["cash_jp"],
        cash_us=portfolio["cash_us"],
        position_count=len(positions),
        week_trades=len(week_trades),
        week_buys=week_buys,
        week_sells=week_sells,
        usdjpy=usdjpy,
    )


def create_scheduler(interval_minutes: int = 15) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="Asia/Tokyo")
    scheduler.add_job(_jp_cycle, "interval", minutes=interval_minutes, id="jp_cycle")
    scheduler.add_job(_us_cycle, "interval", minutes=interval_minutes, id="us_cycle")
    # 毎週月曜 8:00 JST に週次レポート
    scheduler.add_job(_weekly_report, "cron", day_of_week="mon", hour=8, minute=0, id="weekly_report")
    return scheduler
