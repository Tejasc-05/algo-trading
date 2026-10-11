from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, String, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, TimestampMixin, uuid_pk, JSONVariant
from app.database.models.enums import OrderSide, OrderStatus, OrderType, TradingMode


class PaperAccount(Base, TimestampMixin):
    """A simulated trading account. Never places real exchange orders — see
    app.paper_trading (Phase 7) for the simulation engine. A user may have
    multiple paper accounts (e.g. one per strategy)."""

    __tablename__ = "paper_accounts"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    strategy_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    strategy_version_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("strategy_versions.id", ondelete="SET NULL"), nullable=True)
    last_processed_bar: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    market_type: Mapped[str] = mapped_column(String(16), default="spot", server_default="spot", nullable=False)
    leverage: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    fee_rate: Mapped[float] = mapped_column(Numeric(12, 8), default=0.001, server_default="0.001", nullable=False)
    slippage_rate: Mapped[float] = mapped_column(Numeric(12, 8), default=0.0005, server_default="0.0005", nullable=False)
    maintenance_margin_rate: Mapped[float] = mapped_column(Numeric(12, 8), default=0.005, server_default="0.005", nullable=False)
    funding_rate: Mapped[float] = mapped_column(Numeric(12, 8), default=0.0001, server_default="0.0001", nullable=False)
    diagnostics: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Paper Account", server_default="Paper Account")
    currency: Mapped[str] = mapped_column(String(16), nullable=False, default="USDT", server_default="USDT")
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, default="BTC/USDT", server_default="BTC/USDT")
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False, default="1h", server_default="1h")
    starting_balance: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    balance: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)


class Order(Base, TimestampMixin):
    """An order, paper or live. `paper_account_id` is set for paper mode,
    `exchange_connection_id` for live mode — exactly one should be set,
    enforced at the service layer (Phase 5/7), not the DB."""

    __tablename__ = "orders"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    strategy_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    paper_account_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("paper_accounts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    exchange_connection_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("exchange_connections.id", ondelete="SET NULL"), nullable=True, index=True
    )
    mode: Mapped[TradingMode] = mapped_column(Enum(TradingMode, native_enum=False), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    side: Mapped[OrderSide] = mapped_column(Enum(OrderSide, native_enum=False), nullable=False)
    order_type: Mapped[OrderType] = mapped_column(Enum(OrderType, native_enum=False), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, native_enum=False), nullable=False, default=OrderStatus.PENDING, server_default="PENDING", index=True
    )
    quantity: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    price: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)

    risk_params: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)

    trades: Mapped[list["Trade"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class Trade(Base, TimestampMixin):
    """A fill (or partial fill) against an Order."""

    __tablename__ = "trades"

    id: Mapped[str] = uuid_pk()
    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    executed_price: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    executed_quantity: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    fee: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False, default=0, server_default="0")
    pnl: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    order: Mapped["Order"] = relationship(back_populates="trades")


class PaperEquitySnapshot(Base):
    __tablename__ = "paper_equity_snapshots"
    id: Mapped[str] = uuid_pk()
    paper_account_id: Mapped[str] = mapped_column(String(36), ForeignKey("paper_accounts.id", ondelete="CASCADE"), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    equity: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
