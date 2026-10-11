from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from app.database.models.base import Base, JSONVariant, TimestampMixin, uuid_pk


class DemoSession(Base, TimestampMixin):
    __tablename__ = 'futures_demo_sessions'
    __table_args__ = (Index('uq_demo_active_connection', 'connection_id', unique=True,
        postgresql_where=text("status != 'stopped'"), sqlite_where=text("status != 'stopped'")),)
    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    connection_id: Mapped[str] = mapped_column(ForeignKey('exchange_connections.id'), nullable=False)
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey('strategy_versions.id'), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    max_notional: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    loss_limit: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    starting_equity: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    last_bar: Mapped[str | None] = mapped_column(String(40))
    lease_owner: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    message: Mapped[str | None] = mapped_column(String(255))
    diagnostics: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)


class DemoOrder(Base, TimestampMixin):
    __tablename__ = 'futures_demo_orders'
    __table_args__ = (UniqueConstraint('client_id', name='uq_demo_client_id'),)
    id: Mapped[str] = uuid_pk()
    session_id: Mapped[str] = mapped_column(ForeignKey('futures_demo_sessions.id'), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(String(36), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    params: Mapped[dict] = mapped_column(JSONVariant, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONVariant)
