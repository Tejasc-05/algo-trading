"""Import every model module so their tables register on Base.metadata before
Alembic autogenerate (or Base.metadata.create_all in tests) reads it. This
import is the single source of truth for "which tables exist" — a model
defined in a file that isn't imported here is invisible to migrations.
"""
from app.database.models.base import Base, JSONVariant, TimestampMixin, metadata_obj  # noqa: F401
from app.database.models.user import User  # noqa: F401
from app.database.models.strategy import Strategy, StrategyVersion  # noqa: F401
from app.database.models.exchange_connection import ExchangeConnection  # noqa: F401
from app.database.models.paper_trading import Order, PaperAccount, Trade  # noqa: F401
from app.database.models.portfolio import Portfolio, Position  # noqa: F401
from app.database.models.backtest import Backtest, BacktestResult  # noqa: F401
from app.database.models.futures import DemoSession, DemoOrder  # noqa: F401

__all__ = [
    "Base",
    "JSONVariant",
    "TimestampMixin",
    "metadata_obj",
    "User",
    "Strategy",
    "StrategyVersion",
    "ExchangeConnection",
    "PaperAccount",
    "Order",
    "Trade",
    "Portfolio",
    "Position",
    "Backtest",
    "BacktestResult",
]
