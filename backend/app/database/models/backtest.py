from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, JSONVariant, TimestampMixin, uuid_pk
from app.database.models.enums import BacktestEngine, BacktestStatus


class Backtest(Base, TimestampMixin):
    """A backtest run against one immutable StrategyVersion. The FK uses
    ondelete=RESTRICT (not CASCADE) — this is what actually enforces "never
    destroy a strategy version that has backtest history" at the DB level."""

    __tablename__ = "backtests"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    strategy_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("strategy_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    engine: Mapped[BacktestEngine] = mapped_column(Enum(BacktestEngine, native_enum=False), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    starting_capital: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    fees: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, default=0, server_default="0")
    slippage: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, default=0, server_default="0")
    status: Mapped[BacktestStatus] = mapped_column(
        Enum(BacktestStatus, native_enum=False), nullable=False, default=BacktestStatus.PENDING, server_default="PENDING", index=True
    )

    result: Mapped["BacktestResult | None"] = relationship(back_populates="backtest", cascade="all, delete-orphan")


class BacktestResult(Base, TimestampMixin):
    """Computed metrics for a completed Backtest. One-to-one with Backtest.

    Backtesting results are historical simulations only and are never a
    guarantee of future performance.
    """

    __tablename__ = "backtest_results"

    id: Mapped[str] = uuid_pk()
    backtest_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("backtests.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    total_return_pct: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False)
    net_profit: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    win_rate_pct: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    num_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    max_drawdown_pct: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    sharpe_ratio: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    profit_factor: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    final_portfolio_value: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    equity_curve_json: Mapped[list] = mapped_column(JSONVariant, nullable=False)
    trade_history_json: Mapped[list] = mapped_column(JSONVariant, nullable=False)

    backtest: Mapped["Backtest"] = relationship(back_populates="result")
