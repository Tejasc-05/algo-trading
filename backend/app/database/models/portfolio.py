from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, TimestampMixin, uuid_pk
from app.database.models.enums import PositionSide


class Portfolio(Base, TimestampMixin):
    """Aggregated holdings view for a user, optionally scoped to one paper
    account. Live-trading portfolios (Phase 10) reuse the same table."""

    __tablename__ = "portfolios"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paper_account_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("paper_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Default Portfolio", server_default="Default Portfolio")

    positions: Mapped[list["Position"]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")


class Position(Base, TimestampMixin):
    __tablename__ = "positions"

    id: Mapped[str] = uuid_pk()
    portfolio_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    side: Mapped[PositionSide] = mapped_column(Enum(PositionSide, native_enum=False), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    average_entry_price: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true", index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stop_loss: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    last_mark_price: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="positions")
