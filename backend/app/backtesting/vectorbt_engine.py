"""Primary vectorized-style backtesting engine."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import pandas as pd

from app.backtesting.library_adapters import vectorbt_simulate
from app.market_data.historical import fetch_historical_ohlcv


async def run_vectorbt_backtest(
    strategy_graph: Any,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    starting_capital: float,
    fees_pct: float,
    slippage_pct: float,
    candles: pd.DataFrame | None = None,
) -> dict[str, Any]:
    df = candles
    if df is None:
        df = await fetch_historical_ohlcv(symbol=symbol, timeframe=timeframe, start=start, end=end)
    if df is None or df.empty:
        raise ValueError(f"No historical data available for {symbol} {timeframe}")

    return await asyncio.to_thread(vectorbt_simulate,
        strategy_graph,
        df,
        symbol=symbol,
        timeframe=timeframe,
        starting_capital=starting_capital,
        fees_pct=fees_pct,
        slippage_pct=slippage_pct,
    )
