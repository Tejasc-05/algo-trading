"""Request/response contracts for owned trading accounts and portfolios."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict

from app.database.models.enums import OrderSide, OrderStatus, PositionSide


class PaperTradingStartRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    strategy_id: str
    symbol: str = Field(pattern=r"^[A-Z0-9]{1,12}/[A-Z0-9]{1,12}$")
    timeframe: Literal["1m", "5m", "15m", "1h", "4h", "1d"] = "1h"
    starting_balance: float = Field(default=10_000, gt=0, le=1_000_000_000)
    market_type: Literal["spot", "futures"] = "spot"
    leverage: int = Field(default=1, ge=1, le=10)
    fee_rate: float = Field(default=0.001, ge=0, le=0.01)
    slippage_rate: float = Field(default=0.0005, ge=0, le=0.01)
    funding_rate: float = Field(default=0.0001, ge=-0.01, le=0.01)
    maintenance_margin_rate: float = Field(default=0.005, ge=0.001, le=0.05)


class PaperAccountOut(BaseModel):
    name: str = "Paper Account"
    market_type: str = "spot"
    leverage: int = 1
    fee_rate: float = 0.001
    slippage_rate: float = 0.0005
    funding_rate: float = 0.0001
    maintenance_margin_rate: float = 0.005
    margin_used: float = 0
    diagnostics: dict | None = None
    strategy_version_id: str | None = None
    equity: float | None = None
    id: str
    strategy_id: str | None
    currency: str
    symbol: str | None = None
    timeframe: str | None = None
    balance: float
    starting_balance: float
    total_pnl: float
    total_pnl_percent: float
    is_active: bool


class PaperTradeOut(BaseModel):
    id: str
    symbol: str
    side: OrderSide
    status: OrderStatus
    quantity: float
    price: float | None
    pnl: float | None
    fee: float = 0
    executed_at: datetime | None


class ExchangeConnectRequest(BaseModel):
    exchange_name: str = Field(min_length=1, max_length=64, description="CCXT exchange id, e.g. 'binance'")
    label: str | None = Field(default=None, max_length=255)
    api_key: str = Field(min_length=1, max_length=4096)
    api_secret: str = Field(min_length=1, max_length=4096)
    passphrase: str | None = Field(default=None, max_length=4096)
    is_testnet: bool = True


class ExchangeConnectionOut(BaseModel):
    """Never includes api_key/api_secret — credentials are write-only."""

    id: str
    exchange_name: str
    label: str | None
    is_testnet: bool
    is_active: bool
    created_at: datetime


class PositionOut(BaseModel):
    id: str
    symbol: str
    side: PositionSide
    quantity: float
    average_entry_price: float
    margin: float = 0
    liquidation_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    funding_paid: float = 0
    current_price: float | None
    pnl: float | None
    pnl_percent: float | None


class PortfolioOut(BaseModel):
    weekly_pnl: float = 0
    weekly_pnl_percent: float = 0
    total_return_pct: float = 0
    total_value: float
    cash_balance: float
    daily_pnl: float
    daily_pnl_percent: float
    positions: list[PositionOut]


class EquityCurvePoint(BaseModel):
    date: datetime
    value: float


class PortfolioPerformanceOut(BaseModel):
    equity_curve: list[EquityCurvePoint]
    win_rate_pct: float | None
    sharpe_ratio: float | None
    max_drawdown_pct: float | None
