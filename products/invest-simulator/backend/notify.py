import os
import requests
from datetime import datetime
from typing import Optional


def send_telegram(message: str) -> bool:
    """Telegramにメッセージを送信する。失敗してもクラッシュしない。"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        return r.status_code == 200
    except Exception:
        return False


def notify_trade(action: str, ticker: str, market: str, shares: int, price: float,
                 reason: str, pnl: Optional[float] = None) -> None:
    """BUY / SELL 成立時の通知。"""
    market_label = "🇯🇵 日本株" if market == "JP" else "🇺🇸 米国株"
    if action == "BUY":
        body = f"<b>🟢 買い注文成立</b> [{market_label}]\n"
        body += f"銘柄: {ticker}\n"
        body += f"株数: {shares}株\n"
        body += f"約定価格: ${price:.2f}\n"
        body += f"理由: {reason}"
    elif action == "SELL":
        pnl_line = ""
        if pnl is not None:
            pnl_sign = "+" if pnl >= 0 else ""
            pnl_line = f"損益: {pnl_sign}${pnl:.2f}\n"
        body = f"<b>🔴 売り注文成立</b> [{market_label}]\n"
        body += f"銘柄: {ticker}\n"
        body += f"株数: {shares}株\n"
        body += f"約定価格: ${price:.2f}\n"
        body += pnl_line
        body += f"理由: {reason}"
    else:
        return
    send_telegram(body)


def notify_weekly_report(
    total_value: float,
    pnl: float,
    pnl_pct: float,
    cash_jp: float,
    cash_us: float,
    position_count: int,
    week_trades: int,
    week_buys: int,
    week_sells: int,
    usdjpy: float,
) -> None:
    """週次パフォーマンスレポートを送信する（毎週月曜 8:00 JST）。"""
    pnl_sign = "+" if pnl >= 0 else ""
    pnl_emoji = "📈" if pnl >= 0 else "📉"
    total_jpy = total_value * usdjpy

    msg = f"<b>📊 週次パフォーマンスレポート</b>\n"
    msg += f"{datetime.now().strftime('%Y-%m-%d')} (月曜 週始め)\n\n"
    msg += f"{pnl_emoji} <b>総資産:</b> ${total_value:,.2f} (≈¥{total_jpy:,.0f})\n"
    msg += f"<b>損益:</b> {pnl_sign}${pnl:.2f} ({pnl_sign}{pnl_pct:.2f}%)\n\n"
    msg += f"<b>内訳</b>\n"
    msg += f"  現金(JPY枠): ${cash_jp:.2f}\n"
    msg += f"  現金(USD枠): ${cash_us:.2f}\n"
    msg += f"  保有銘柄数: {position_count}銘柄\n\n"
    msg += f"<b>先週の取引</b>\n"
    msg += f"  計: {week_trades}件 (買:{week_buys} / 売:{week_sells})"
    send_telegram(msg)
