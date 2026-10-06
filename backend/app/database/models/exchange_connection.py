from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, TimestampMixin, uuid_pk


class ExchangeConnection(Base, TimestampMixin):
    """A user's link to an exchange via CCXT. API credentials are stored only
    as Fernet ciphertext (see app.core.security.encrypt_secret) — never in
    plain text, never returned by any API response.

    `exchange_name` is a free-form string validated against CCXT's supported
    exchange ids at the Pydantic layer rather than a DB enum/CHECK, so
    supporting a new exchange never requires a migration.
    """

    __tablename__ = "exchange_connections"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exchange_name: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    api_secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    passphrase_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_testnet: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)

    user: Mapped["User"] = relationship()
