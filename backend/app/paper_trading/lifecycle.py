"""Account mutation helpers. Acquire the account lock before any order lock."""
from datetime import datetime, timezone
from sqlalchemy import select
from app.core.exceptions import AppError
from app.database.models.paper_trading import PaperAccount, Order
from app.database.models.enums import OrderStatus
from app.paper_trading.portfolio import list_open_positions
from app.paper_trading.engine import note, _spot_order
from app.paper_trading.futures import close_position, apply_funding
from app.paper_trading.market import fetch_futures_ohlcv
from app.market_data.historical import fetch_latest_ohlcv
from app.paper_trading.account_views import snapshot


async def owned_account(db, user_id, account_id, *, lock=False):
    stmt = select(PaperAccount).where(PaperAccount.id == account_id, PaperAccount.user_id == user_id)
    if lock: stmt = stmt.with_for_update().execution_options(populate_existing=True)
    account = (await db.execute(stmt)).scalar_one_or_none()
    if account is None: raise AppError('ACCOUNT_NOT_FOUND', 'Paper account not found', 404)
    return account


async def stop_account(db, account, *, close_positions=False):
    positions = await list_open_positions(db, account)
    if close_positions and positions:
        # Read public market data; never trust a client-supplied closing price.
        fetch = fetch_futures_ohlcv if account.market_type == 'futures' else fetch_latest_ohlcv
        frame = await fetch(account.symbol, account.timeframe, limit=5)
        if frame is None or frame.empty:
            raise AppError('MARKET_DATA_UNAVAILABLE', 'Cannot close simulated positions without a market price.', 503)
        from app.market_data.historical import TIMEFRAME_DELTA
        stamp = frame.iloc[-1].timestamp.to_pydatetime()
        if stamp < datetime.now(timezone.utc) - TIMEFRAME_DELTA[account.timeframe] * 2:
            raise AppError('STALE_MARKET_DATA', 'Cannot close simulated positions using stale candles.', 503)
        price = float(frame.iloc[-1]['close'])
        # The enclosing transaction holds the account lock. Temporarily enable
        # settlement for a previously paused account, then pause before commit.
        account.is_active = True
        await db.flush()
        for position in positions:
            if account.market_type == 'futures':
                apply_funding(account, position, datetime.now(timezone.utc), price)
                await close_position(db, account, position, price)
            else:
                await _spot_order(db, account, 'sell', float(position.quantity), price)
    pending = list((await db.execute(select(Order).where(Order.paper_account_id == account.id,
        Order.status == OrderStatus.PENDING))).scalars())
    for order in pending: order.status = OrderStatus.CANCELLED
    account.is_active = False
    note(account, 'STOPPED_FLAT' if close_positions else 'STOPPED',
        'Stopped; all simulated positions closed and pending orders cancelled.' if close_positions else
        'Paused; pending orders cancelled. Existing positions remain open and protection is paused.', last_error=None)
    await snapshot(db, account)
    await db.commit()
    from app.redis.pubsub import publish_user_event
    await publish_user_event(account.user_id, 'portfolio_update', {'paper_account_id': account.id})
