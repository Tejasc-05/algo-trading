"""Local isolated USDT futures accounting, one position per paper account.

Funding uses the configured scenario rate at 00/08/16 UTC. It is not an
exchange funding-rate forecast. Liquidation uses a fixed maintenance ratio.
"""
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from math import isfinite
from app.core.exceptions import AppError
from app.database.models.enums import OrderSide, OrderType, OrderStatus, PositionSide, TradingMode
from app.database.models.paper_trading import Order, Trade
from app.database.models.portfolio import Position
from app.paper_trading.portfolio import _ensure_portfolio, list_open_positions
from app.paper_trading.simulator import simulate_fill
from app.paper_trading.risk import unrealized


async def record_fill(db, account, side, fill):
    order = Order(user_id=account.user_id, strategy_id=account.strategy_id,
        paper_account_id=account.id, mode=TradingMode.PAPER, symbol=account.symbol,
        side=OrderSide(side), order_type=OrderType.MARKET, status=OrderStatus.FILLED,
        quantity=fill['executed_quantity'], price=fill['executed_price'])
    db.add(order)
    await db.flush()
    trade = Trade(order_id=order.id, executed_at=datetime.now(timezone.utc), **fill)
    db.add(trade)
    await db.flush()
    return trade


def simulated_fill(account, side, quantity, price):
    return simulate_fill(SimpleNamespace(side=side, quantity=quantity), price,
        fee_pct=float(account.fee_rate), slippage_pct=float(account.slippage_rate))


async def open_position(db, account, side, quantity, price):
    if side not in {'long', 'short'} or not isfinite(quantity) or quantity <= 0:
        raise AppError('INVALID_QUANTITY', 'Futures quantity must be positive and finite.', 422)
    if await list_open_positions(db, account):
        raise AppError('POSITION_OPEN', 'This futures paper account already has an open position.', 409)
    fill = simulated_fill(account, 'buy' if side == 'long' else 'sell', quantity, price)
    margin = fill['executed_price'] * quantity / account.leverage
    if margin + fill['fee'] > float(account.balance):
        raise AppError('INSUFFICIENT_MARGIN', 'Insufficient virtual margin including entry fee.', 409)
    account.balance = float(account.balance) - margin - fill['fee']
    portfolio = await _ensure_portfolio(db, account)
    position = Position(portfolio_id=portfolio.id, symbol=account.symbol,
        side=PositionSide(side), quantity=quantity, average_entry_price=fill['executed_price'],
        last_mark_price=price, is_open=True, margin_balance=margin,
        entry_fee=fill['fee'], funding_paid=0, opened_at=datetime.now(timezone.utc),
        last_funding_at=datetime.now(timezone.utc))
    db.add(position)
    trade = await record_fill(db, account, 'buy' if side == 'long' else 'sell', fill)
    return position, trade


async def close_position(db, account, position, price, *, liquidated=False):
    side = 'sell' if position.side == PositionSide.LONG else 'buy'
    fill = simulated_fill(account, side, float(position.quantity), price)
    gross = unrealized(position, fill['executed_price'])
    refund = 0 if liquidated else max(0, float(position.margin_balance) + gross - fill['fee'])
    # Net cash flow includes opening fees and every signed funding payment.
    fill['pnl'] = refund - float(position.margin_balance) - float(position.funding_paid) - float(position.entry_fee)
    account.balance = float(account.balance) + refund
    position.quantity = 0
    position.is_open = False
    position.closed_at = datetime.now(timezone.utc)
    position.margin_balance = 0
    return await record_fill(db, account, side, fill)


def apply_funding(account, position, through, price):
    """Apply each crossed UTC 8-hour boundary once, persisted with the position."""
    last = (position.last_funding_at or position.opened_at).replace(tzinfo=timezone.utc)
    boundary = last.replace(hour=(last.hour // 8) * 8, minute=0, second=0, microsecond=0) + timedelta(hours=8)
    amount = 0.0
    while boundary <= through:
        payment = float(position.quantity) * price * float(account.funding_rate)
        if position.side == PositionSide.SHORT:
            payment = -payment
        # Isolated collateral caps a debit; exhaustion triggers liquidation.
        payment = min(payment, max(0, float(position.margin_balance)))
        position.margin_balance = float(position.margin_balance) - payment
        position.funding_paid = float(position.funding_paid) + payment
        amount += payment
        position.last_funding_at = boundary
        boundary += timedelta(hours=8)
    return amount
