"""Transactional paper order settlement; PostgreSQL serializes account mutations."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.database.models.enums import OrderStatus, TradingMode
from app.database.models.paper_trading import Order, PaperAccount, Trade
from app.paper_trading.portfolio import apply_fill_to_portfolio
from app.paper_trading.simulator import simulate_fill


async def settle_order(db: AsyncSession, order_id: str, user_id: str, current_price: float) -> Trade:
    order = (await db.execute(select(Order).where(
        Order.id == order_id, Order.user_id == user_id, Order.mode == TradingMode.PAPER
    ))).scalar_one_or_none()
    if order is None:
        raise AppError("ORDER_NOT_FOUND", "Paper order not found", 404)
    account = (await db.execute(select(PaperAccount).where(
        PaperAccount.id == order.paper_account_id, PaperAccount.user_id == user_id
    ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if account is None or not account.is_active:
        raise AppError("ACCOUNT_INACTIVE", "Paper account is inactive", 409)
    # Always acquire account before order locks, including worker execution.
    order = (await db.execute(select(Order).where(Order.id == order_id)
        .with_for_update().execution_options(populate_existing=True))).scalar_one()
    if order.status != OrderStatus.PENDING:
        raise AppError("ORDER_ALREADY_SETTLED", "Order is no longer pending", 409)
    fill = simulate_fill(order, current_price)
    await apply_fill_to_portfolio(db, account, symbol=order.symbol, side=order.side.value, fill=fill)
    trade = Trade(order_id=order.id, executed_at=datetime.now(timezone.utc), **fill)
    db.add(trade)
    order.status = OrderStatus.FILLED
    await db.flush()
    return trade
