"""Real quant-library adapters behind the existing result contract.

VectorBT replays the reference simulator's graph/risk fill plan through its
portfolio engine. Backtrader independently runs market-only spot graphs.
Neither adapter silently substitutes another engine.
"""
import numpy as np
import pandas as pd

from app.backtesting.metrics import compute_metrics
from app.backtesting.simulator import simulate_strategy_on_ohlcv
from app.core.exceptions import AppError
from app.market_data.historical import normalize_ohlcv
from app.strategy_engine.executor import StrategyExecutor


def vectorbt_simulate(graph, candles, **options):
    try:
        import vectorbt as vbt
    except ImportError as exc:
        raise AppError("ENGINE_UNAVAILABLE", "Install requirements-quant.txt to use VectorBT", 503) from exc
    if any(n.data.params.get("type") == "limit" for n in graph.nodes):
        raise AppError("ENGINE_CAPABILITY_UNSUPPORTED", "Limit backtesting is not supported by this adapter", 422)
    planned = simulate_strategy_on_ohlcv(graph, candles, **options)
    # Retain individual fills when multiple risk/action orders occur in a bar.
    fills = planned["trade_history"]
    # Simulate fills separately and verify cash/holdings against the reference.
    df = normalize_ohlcv(candles)
    close, size, price, stamps = [], [], [], []
    for row in df.itertuples():
        bar_fills = [f for f in fills if pd.Timestamp(f["timestamp"]) == row.timestamp]
        for fill in bar_fills:
            close.append(float(row.close))
            size.append(fill["quantity"] * (1 if fill["side"] == "buy" else -1))
            price.append(fill["price"])
            stamps.append(row.timestamp)
        close.append(float(row.close)); size.append(0.0); price.append(float(row.close)); stamps.append(row.timestamp)
    portfolio = vbt.Portfolio.from_orders(
        close=pd.Series(close), size=np.asarray(size), price=np.asarray(price),
        fees=options["fees_pct"], slippage=0.0, init_cash=options["starting_capital"],
        direction="longonly", allow_partial=False,
    )
    values = np.asarray(portfolio.value(), dtype=float)
    curve = [{"timestamp": stamps[0], "value": options["starting_capital"]}]
    for stamp, value in zip(stamps, values):
        point = {"timestamp": stamp.to_pydatetime(), "value": round(float(value), 2)}
        if len(curve) > 1 and curve[-1]["timestamp"] == point["timestamp"]:
            curve[-1] = point
        else:
            curve.append(point)
    if abs(curve[-1]["value"] - planned["metrics"]["final_portfolio_value"]) > 0.05:
        raise AppError("ENGINE_RECONCILIATION_FAILED", "VectorBT portfolio disagrees with the fill plan", 500)
    return {"metrics": compute_metrics(curve, fills, options["starting_capital"]), "equity_curve": curve, "trade_history": fills}


def backtrader_simulate(graph, candles, **options):
    try:
        import backtrader as bt
    except ImportError as exc:
        raise AppError("ENGINE_UNAVAILABLE", "Install requirements-quant.txt to use Backtrader", 503) from exc
    if any(n.data.node_type in {"stopLoss", "takeProfit"} or n.data.params.get("type") == "limit" for n in graph.nodes):
        raise AppError("ENGINE_CAPABILITY_UNSUPPORTED", "Backtrader adapter supports market-only spot graphs; use VectorBT for risk nodes", 422)
    df = normalize_ohlcv(candles)
    executor = StrategyExecutor(graph)
    history, curve = [], []

    class GraphStrategy(bt.Strategy):
        def __init__(self):
            self.pending = None

        def notify_order(self, order):
            if order.status == order.Completed:
                history.append({"timestamp": bt.num2date(order.executed.dt),
                    "side": "buy" if order.isbuy() else "sell", "price": float(order.executed.price),
                    "quantity": abs(float(order.executed.size)), "pnl": None})
            if order.status in {order.Completed, order.Canceled, order.Margin, order.Rejected}:
                self.pending = None

        def notify_trade(self, trade):
            if trade.isclosed and history:
                history[-1]["pnl"] = float(trade.pnlcomm)

        def next(self):
            i = len(self.data)
            curve.append({"timestamp": df.iloc[i - 1].timestamp.to_pydatetime(), "value": float(self.broker.getvalue())})
            if self.pending is not None:
                return
            signals = executor.evaluate({"candles": df.iloc[:i], "sentiment": None})
            actions = [s for s in signals if s.action in {"buy", "sell"}]
            action = actions[0] if len(actions) == 1 else None
            if action is None:
                return
            amount = float(action.params.get("amount", 0.1))
            if action.action == "buy" and self.position.size == 0:
                self.pending = self.buy(size=amount)
            elif action.action == "sell" and self.position.size > 0:
                self.pending = self.sell(size=min(amount, self.position.size))

    cerebro = bt.Cerebro(stdstats=False)
    frame = df.set_index("timestamp").copy()
    frame.index = frame.index.tz_localize(None)
    cerebro.adddata(bt.feeds.PandasData(dataname=frame))
    cerebro.addstrategy(GraphStrategy)
    cerebro.broker.setcash(options["starting_capital"])
    cerebro.broker.setcommission(commission=options["fees_pct"])
    cerebro.broker.set_slippage_perc(options["slippage_pct"], slip_open=True)
    cerebro.run()
    return {"metrics": compute_metrics(curve, history, options["starting_capital"]), "equity_curve": curve, "trade_history": history}
