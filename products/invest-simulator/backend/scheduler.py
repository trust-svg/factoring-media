import os
from apscheduler.schedulers.background import BackgroundScheduler
import market
import trader


def _jp_cycle() -> None:
    if market.is_jp_market_open():
        trader.run_trading_cycle("JP")


def _us_cycle() -> None:
    if market.is_us_market_open():
        trader.run_trading_cycle("US")


def create_scheduler(interval_minutes: int = 15) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="Asia/Tokyo")
    scheduler.add_job(_jp_cycle, "interval", minutes=interval_minutes, id="jp_cycle")
    scheduler.add_job(_us_cycle, "interval", minutes=interval_minutes, id="us_cycle")
    return scheduler
