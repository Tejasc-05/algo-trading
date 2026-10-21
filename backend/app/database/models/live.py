from datetime import datetime
from decimal import Decimal
from sqlalchemy import DateTime, ForeignKey, String, Numeric, UniqueConstraint, Index, CheckConstraint, text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database.models.base import Base, uuid_pk, JSONVariant


class LiveAccount(Base):
    __tablename__ = 'live_accounts'
    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    # Exchange-derived identity, independent of how many API keys were saved.
    account_identity: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    connection_id: Mapped[str | None] = mapped_column(ForeignKey('exchange_connections.id', ondelete='SET NULL'), unique=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fence_token: Mapped[str | None] = mapped_column(String(36))


class LiveRun(Base):
    __tablename__ = 'live_runs'
    __table_args__ = (Index('uq_live_active_account', 'account_id', unique=True,
        postgresql_where=text("status != 'stopped'"), sqlite_where=text("status != 'stopped'")),
        CheckConstraint("status != 'stopped' OR active_entry_id IS NULL", name='stopped_without_cycle'))
    id: Mapped[str] = uuid_pk()
    account_id: Mapped[str] = mapped_column(ForeignKey('live_accounts.id'), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey('strategy_versions.id'), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    policy: Mapped[dict] = mapped_column(JSONVariant, nullable=False)
    # This is a durable cycle cursor, not an exchange ID. Kept without a reverse
    # FK to avoid a circular run/order insertion dependency on both dialects.
    active_entry_id: Mapped[str | None] = mapped_column(String(36))
    last_bar: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LiveOrder(Base):
    __tablename__ = 'live_orders'
    __table_args__ = (UniqueConstraint('account_id', 'intent_key', name='uq_live_account_intent'),)
    id: Mapped[str] = uuid_pk()
    account_id: Mapped[str] = mapped_column(ForeignKey('live_accounts.id'), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey('live_runs.id'), nullable=False, index=True)
    cycle_entry_id: Mapped[str] = mapped_column(String(36), nullable=False)
    client_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    intent_key: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    params: Mapped[dict] = mapped_column(JSONVariant, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONVariant)
    filled_quantity: Mapped[Decimal] = mapped_column(Numeric(28, 12), nullable=False, default=0, server_default='0')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LiveEvent(Base):
    __tablename__ = 'live_events'
    id: Mapped[str] = uuid_pk()
    account_id: Mapped[str] = mapped_column(ForeignKey('live_accounts.id'), nullable=False, index=True)
    order_id: Mapped[str | None] = mapped_column(ForeignKey('live_orders.id'))
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[dict] = mapped_column(JSONVariant, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
