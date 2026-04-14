import os
from datetime import datetime
import anthropic
import db
import market as mkt
import notify

TOOLS = [
    {
        "name": "buy_stock",
        "description": "株を購入する",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "shares": {"type": "integer"},
                "reason": {"type": "string"},
            },
            "required": ["ticker", "shares", "reason"],
        },
    },
    {
        "name": "sell_stock",
        "description": "保有株を売却する",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "shares": {"type": "integer"},
                "reason": {"type": "string"},
            },
            "required": ["ticker", "shares", "reason"],
        },
    },
    {
        "name": "hold",
        "description": "今回は売買せず様子を見る",
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },
]

SYSTEM_PROMPT = """あなたは日本株・米国株のAIトレーダーです。
与えられた市場データとポートフォリオ状況を分析し、buy_stock / sell_stock / hold のいずれかを必ず実行してください。

リスク管理ルール:
- 利確ライン: 購入価格比 +8% 以上で売却を検討
- 損切りライン: 購入価格比 -5% 以下で売却を検討
- 1銘柄最大投資: その枠の残金の30%まで
- 現金比率: 常に枠の20%以上を維持（購入時に (購入額) <= (残金 × 0.8) を守る）

判断は必ずツールで実行してください。reason（理由）は日本語で記述してください。"""

JP_CANDIDATES = ["7203.T", "6758.T", "9984.T", "8306.T", "6857.T"]
US_CANDIDATES = ["AAPL", "NVDA", "MSFT", "GOOGL", "AMZN"]


def run_trading_cycle(market: str) -> dict:
    """
    指定市場の売買サイクルを1回実行する。
    market: 'JP' または 'US'
    returns: {"action": str, "details": list}
    """
    portfolio = db.get_portfolio()
    positions = db.get_positions()
    market_positions = [p for p in positions if p["market"] == market]
    cash = portfolio["cash_jp"] if market == "JP" else portfolio["cash_us"]
    candidates = JP_CANDIDATES if market == "JP" else US_CANDIDATES

    usdjpy = mkt.get_usdjpy()
    all_tickers = list(set(candidates + [p["ticker"] for p in market_positions]))
    prices = mkt.get_market_data(all_tickers)

    # 株価データが全く取れなかった場合はAPIを呼ばずにスキップ（DBには記録しない）
    candidate_prices = {t: p for t, p in prices.items() if t in candidates}
    if not candidate_prices:
        mkt.mark_api_failure()
        return {"action": "hold", "details": [{"reason": "株価データ取得失敗（APIレート制限）"}]}

    positions_text = "\n".join(
        f"- {p['ticker']}: {p['shares']}株, 平均取得単価 ${p['avg_cost']:.2f}, "
        f"現在値 ${prices.get(p['ticker'], p['avg_cost']):.2f}, "
        f"損益率 {((prices.get(p['ticker'], p['avg_cost']) / p['avg_cost']) - 1) * 100:.1f}%"
        for p in market_positions
    ) or "なし"

    prices_text = "\n".join(
        f"- {t}: ${p:.2f}" for t, p in candidate_prices.items()
    )

    user_message = (
        f"市場: {'日本株(東証)' if market == 'JP' else '米国株(NYSE/NASDAQ)'}\n"
        f"利用可能現金: ${cash:.2f}\n"
        f"USD/JPY: {usdjpy:.2f}\n\n"
        f"【保有銘柄】\n{positions_text}\n\n"
        f"【候補銘柄の現在値】\n{prices_text}\n\n"
        "売買判断を行ってください。"
    )

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        messages=[{"role": "user", "content": user_message}],
    )

    result = {"action": "hold", "details": []}
    log = {
        "timestamp": datetime.now().isoformat(),
        "market": market,
        "input": user_message,
        "decisions": [],
    }

    for block in response.content:
        if block.type != "tool_use":
            continue
        action = block.name
        inputs = block.input
        ticker = inputs.get("ticker", "")
        shares = inputs.get("shares", 0)
        reason = inputs.get("reason", "")

        if action == "buy_stock":
            price = prices.get(ticker)
            if price and shares > 0 and price * shares <= cash * 0.8:
                db.update_cash(market, -(price * shares))
                db.upsert_position(ticker, market, shares, price)
                db.record_trade(ticker, market, "BUY", shares, price, reason)
                notify.notify_trade("BUY", ticker, market, shares, price, reason)
                cash -= price * shares
                result["action"] = "buy"
                result["details"].append(
                    {"ticker": ticker, "shares": shares, "price": price, "reason": reason}
                )
                log["decisions"].append({"action": "BUY", "ticker": ticker, "shares": shares, "price": price, "reason": reason})

        elif action == "sell_stock":
            price = prices.get(ticker)
            position = db.get_position(ticker)
            if price and position and db.reduce_position(ticker, shares):
                proceeds = price * shares
                pnl = (price - position["avg_cost"]) * shares
                db.update_cash(market, proceeds)
                db.record_trade(ticker, market, "SELL", shares, price, reason, pnl)
                notify.notify_trade("SELL", ticker, market, shares, price, reason, pnl)
                result["action"] = "sell"
                result["details"].append(
                    {"ticker": ticker, "shares": shares, "price": price, "pnl": pnl, "reason": reason}
                )
                log["decisions"].append({"action": "SELL", "ticker": ticker, "shares": shares, "price": price, "pnl": pnl, "reason": reason})

        elif action == "hold":
            db.record_trade("", market, "HOLD", None, None, reason)
            result["action"] = "hold"
            result["details"].append({"reason": reason})
            log["decisions"].append({"action": "HOLD", "reason": reason})

    db.record_cycle_log(log)
    _record_snapshot()

    return result


def _record_snapshot() -> None:
    all_positions = db.get_positions()
    all_prices = mkt.get_market_data([p["ticker"] for p in all_positions]) if all_positions else {}
    updated_portfolio = db.get_portfolio()
    position_value = sum(
        all_prices.get(p["ticker"], p["avg_cost"]) * p["shares"] for p in all_positions
    )
    total = updated_portfolio["cash_jp"] + updated_portfolio["cash_us"] + position_value
    db.record_snapshot(total)
