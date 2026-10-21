"""Shared bar-by-bar strategy simulation used by both backtesting engines."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from app.backtesting.metrics import compute_metrics
from app.market_data.historical import normalize_ohlcv
from app.strategy_engine.executor import StrategyExecutor


def _risk_percent(params: dict[str, Any]) -> float | None:
    for key in ("percent", "pct", "stop_loss_pct", "take_profit_pct"):
        if key in params and params[key] is not None:
            return float(params[key])
    return None


def _timestamp(value: Any) -> datetime:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.to_pydatetime()


def simulate_strategy_on_ohlcv(
    strategy_graph: Any,
    candles: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    starting_capital: float,
    fees_pct: float,
    slippage_pct: float,
) -> dict[str, Any]:
    """`fees_pct` / `slippage_pct` are decimal fractions (0.001 = 0.1%)."""
    df = normalize_ohlcv(candles)
    if df.empty:
        raise ValueError("No valid candles")
    executor = StrategyExecutor(strategy_graph)

    cash = float(starting_capital)
    position_qty = 0.0
    position_side: str | None = None
    entry_price = 0.0
    entry_fee = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None
    trade_history: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = [
        {"timestamp": _timestamp(df.iloc[0]["timestamp"]), "value": round(cash, 2)}
    ]

    def close_position(ts: datetime, price: float, side: str, quantity: float | None = None) -> None:
        nonlocal cash, position_qty, position_side, stop_loss, take_profit, entry_fee
        if position_qty <= 0 or position_side is None:
            return
        closed_qty = position_qty if quantity is None else min(quantity, position_qty)
        allocated_entry_fee = entry_fee * closed_qty / position_qty
        fee = price * closed_qty * fees_pct
        if position_side == "long":
            pnl = (price - entry_price) * closed_qty - fee - allocated_entry_fee
            cash += price * closed_qty - fee
        else:
            pnl = (entry_price - price) * closed_qty - fee - allocated_entry_fee
            cash -= price * closed_qty + fee
        trade_history.append(
            {
                "timestamp": ts,
                "side": side,
                "price": round(price, 8),
                "quantity": round(closed_qty, 8),
                "pnl": round(pnl, 2),
            }
        )
        position_qty -= closed_qty
        entry_fee -= allocated_entry_fee
        if position_qty <= 1e-12:
            position_qty = 0.0
            position_side = None
            stop_loss = None
            take_profit = None

    for i in range(len(df)):
        row = df.iloc[i]
        current_price = float(row["open"])
        ts = _timestamp(row["timestamp"])
        slipped_buy = current_price * (1 + slippage_pct)
        slipped_sell = current_price * (1 - slippage_pct)

        signals = executor.evaluate(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "candles": df.iloc[:i].copy(),
                "current_price": current_price,
                "sentiment": None,
            }
        )

        actions = [s for s in signals if s.action in {'buy', 'sell'}]
        risk_actions = [s.action for s in signals if s.action in {'set_stop_loss', 'set_take_profit'}]
        if len(actions) > 1 or len(risk_actions) != len(set(risk_actions)):
            signals = []
        # Risk nodes can precede action nodes in a valid graph. Attach the
        # triggered protection after entries, independent of canvas ordering.
        signals = sorted(signals, key=lambda s: s.action in {'set_stop_loss', 'set_take_profit'})
        for signal in signals:
            params = dict(signal.params)
            risk_pct = _risk_percent(params)
            if signal.action == "buy" and position_side != "long":
                if position_side == "short":
                    close_position(ts, slipped_buy, "buy")
                amount = float(params.get("amount", 0.1))
                notional = slipped_buy * amount
                fee = notional * fees_pct
                if cash >= notional + fee and amount > 0:
                    cash -= notional + fee
                    position_side = "long"
                    position_qty = amount
                    entry_price = slipped_buy
                    entry_fee = fee
                    trade_history.append(
                        {
                            "timestamp": ts,
                            "side": "buy",
                            "price": round(slipped_buy, 8),
                            "quantity": round(amount, 8),
                            "pnl": None,
                        }
                    )
                    if risk_pct is not None:
                        stop_loss = entry_price * (1 - risk_pct / 100.0)
            elif signal.action == "sell" and position_side != "short":
                if position_side == "long":
                    close_position(ts, slipped_sell, "sell", float(params.get('amount', 0.1)))
            elif signal.action == "set_stop_loss" and position_side and position_qty > 0:
                pct = _risk_percent(params)
                if pct is not None:
                    if position_side == "long":
                        stop_loss = entry_price * (1 - pct / 100.0)
                    else:
                        stop_loss = entry_price * (1 + pct / 100.0)
                elif params.get("price") is not None:
                    stop_loss = float(params["price"])
            elif signal.action == "set_take_profit" and position_side and position_qty > 0:
                pct = _risk_percent(params)
                if pct is not None:
                    if position_side == "long":
                        take_profit = entry_price * (1 + pct / 100.0)
                    else:
                        take_profit = entry_price * (1 - pct / 100.0)
                elif params.get("price") is not None:
                    take_profit = float(params["price"])

        if position_side == "long" and position_qty > 0:
            if stop_loss is not None and float(row["low"]) <= stop_loss:
                close_position(ts, min(current_price, stop_loss) * (1 - slippage_pct), "sell")
            elif take_profit is not None and float(row["high"]) >= take_profit:
                close_position(ts, max(current_price, take_profit) * (1 - slippage_pct), "sell")
        elif position_side == "short" and position_qty > 0:
            if stop_loss is not None and current_price >= stop_loss:
                close_position(ts, stop_loss, "buy")
            elif take_profit is not None and current_price <= take_profit:
                close_position(ts, take_profit, "buy")

        if position_side == "long" and position_qty > 0:
            equity = cash + position_qty * float(row["close"])
        elif position_side == "short" and position_qty > 0:
            equity = cash + (entry_price - current_price) * position_qty
        else:
            equity = cash
        equity_curve.append({"timestamp": ts, "value": round(float(equity), 2)})

    last_ts = _timestamp(df.iloc[-1]["timestamp"])
    last_price = float(df.iloc[-1]["close"])
    if position_side == "long":
        close_position(last_ts, last_price * (1 - slippage_pct), "sell")
    elif position_side == "short":
        close_position(last_ts, last_price * (1 + slippage_pct), "buy")

    equity_curve[-1]["value"] = round(cash, 2)
    metrics = compute_metrics(equity_curve, trade_history, starting_capital)
    return {"metrics": metrics, "equity_curve": equity_curve, "trade_history": trade_history}
