"""Request/response contracts for backtesting endpoints. Real implementation
(VectorBT/Backtrader) lands in Phase 6 — routes currently return 501.

Backtest results are historical simulations only and are never a guarantee
of future performance.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict, model_validator

from app.database.models.enums import BacktestStatus


class BacktestRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    strategy_id: str
    strategy_version: int | None = Field(default=None, description="Defaults to the latest saved version")
    symbol: str
    timeframe: str = "1h"
    start_date: datetime
    end_date: datetime
    starting_capital: float = Field(default=10_000, gt=0)
    fees_pct: float = Field(default=0.1, ge=0, lt=100)
    slippage_pct: float = Field(default=0.05, ge=0, lt=100)
    engine: Literal["vectorbt", "backtrader"] = "vectorbt"

    @model_validator(mode="after")
    def validate_dates(self):
        from datetime import timezone
        from app.market_data.historical import TIMEFRAME_DELTA
        self.start_date = self.start_date.replace(tzinfo=timezone.utc) if self.start_date.tzinfo is None else self.start_date.astimezone(timezone.utc)
        self.end_date = self.end_date.replace(tzinfo=timezone.utc) if self.end_date.tzinfo is None else self.end_date.astimezone(timezone.utc)
        if self.timeframe not in TIMEFRAME_DELTA:
            raise ValueError("Unsupported timeframe")
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        if (self.end_date - self.start_date) / TIMEFRAME_DELTA[self.timeframe] > 10000:
            raise ValueError("Maximum backtest range is 10000 candles")
        return self


class TradeHistoryItem(BaseModel):
    timestamp: datetime
    side: Literal["buy", "sell"]
    price: float
    quantity: float
    pnl: float | None


class EquityCurvePoint(BaseModel):
    timestamp: datetime
    value: float


class BacktestMetricsOut(BaseModel):
    total_return_pct: float
    net_profit: float
    win_rate_pct: float
    num_trades: int
    max_drawdown_pct: float
    sharpe_ratio: float | None
    profit_factor: float | None
    final_portfolio_value: float


class BacktestResultOut(BaseModel):
    id: str
    status: BacktestStatus
    metrics: BacktestMetricsOut | None
    equity_curve: list[EquityCurvePoint]
    trade_history: list[TradeHistoryItem]
