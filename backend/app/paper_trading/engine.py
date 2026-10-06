"""Simulated trading engine: evaluates an active strategy against market data.

Paper trading NEVER sends real orders to an exchange.
"""
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.database.models.enums import OrderSide, OrderStatus, OrderType, TradingMode
from app.database.models.paper_trading import Order, PaperAccount, Trade
from app.market_data.historical import fetch_latest_ohlcv
from app.paper_trading.portfolio import apply_fill_to_portfolio
from app.paper_trading.simulator import simulate_fill
from app.strategy_engine.executor import StrategyExecutor

logger = get_logger(__name__)


async def run_paper_trading_tick(
    db: AsyncSession,
    account: PaperAccount,
    strategy_graph: Any,
    symbol: str,
    timeframe: str = "1h",
) -> dict[str, Any]:
    df = await fetch_latest_ohlcv(symbol=symbol, timeframe=timeframe, limit=120)
    if df is None or df.empty:
        raise AppError(
            code="MARKET_DATA_UNAVAILABLE",
            message="No market data available for paper trading",
            status_code=503,
        )

    if not account.is_active:
        raise AppError("ACCOUNT_INACTIVE", "Paper account is inactive", 409)
    from app.market_data.historical import TIMEFRAME_DELTA
    import pandas as pd
    delta = TIMEFRAME_DELTA.get(timeframe)
    if delta is None:
        raise AppError("INVALID_TIMEFRAME", "Unsupported timeframe", 422)
    df = df[df.timestamp + delta <= pd.Timestamp.now(tz="UTC")]
    if df.empty:
        return {"signal": None, "order": None, "message": "Waiting for a closed candle"}
    account = (await db.execute(select(PaperAccount).where(PaperAccount.id == account.id)
        .with_for_update().execution_options(populate_existing=True))).scalar_one()
    if not account.is_active:
        raise AppError("ACCOUNT_INACTIVE", "Paper account is inactive", 409)
    stamp = df.iloc[-1].timestamp.to_pydatetime()
    previous = account.last_processed_bar
    if previous and stamp <= previous.replace(tzinfo=timezone.utc):
        return {"signal": None, "order": None, "message": "Candle already processed"}
    account.last_processed_bar = stamp
    current_price = float(df.iloc[-1]["close"])
    from app.paper_trading.portfolio import list_open_positions
    positions = await list_open_positions(db, account)
    for position in positions:
        position.last_mark_price = current_price

    from app.paper_trading.service import settle_order
    pending = list((await db.execute(select(Order).where(Order.paper_account_id == account.id,
        Order.status == OrderStatus.PENDING))).scalars())
    for pending_order in pending:
        try:
            await settle_order(db, pending_order.id, account.user_id, current_price)
        except AppError as exc:
            if exc.code not in {"LIMIT_NOT_REACHED", "INSUFFICIENT_BALANCE", "INSUFFICIENT_POSITION"}:
                raise
            if exc.code != "LIMIT_NOT_REACHED":
                pending_order.status = OrderStatus.REJECTED
    positions = await list_open_positions(db, account)
    executor = StrategyExecutor(strategy_graph)
    signals = executor.evaluate(
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "candles": df,
            "current_price": current_price,
            "sentiment": None,
        }
    )

    actionable = next((s for s in signals if s.action in ("buy", "sell")), None)
    from app.strategy_engine.executor import Signal
    for position in positions:
        if (position.stop_loss and current_price <= float(position.stop_loss)) or (position.take_profit and current_price >= float(position.take_profit)):
            actionable = Signal("risk_exit", "sell", {"amount": float(position.quantity), "type": "market"})

    if actionable is None:
        await db.commit()
        return {"signal": None, "order": None, "message": "No trading signal generated", "price": current_price}

    side = actionable.action
    amount = float(actionable.params.get("amount", 0.1))
    order_type = str(actionable.params.get("type", "market"))
    max_affordable = max(float(account.balance) * 0.95 / current_price, 0)
    quantity = min(amount, max_affordable) if side == "buy" else amount
    if side == "buy" and (positions or any(o.status == OrderStatus.PENDING for o in pending)):
        await db.commit()
        return {"signal": None, "order": None, "message": "Spot position is already open", "price": current_price}
    if side == "sell":
        quantity = min(quantity, sum(float(p.quantity) for p in positions))
    if quantity <= 0:
        await db.commit()
        return {"signal": None, "order": None, "message": "Insufficient paper balance", "price": current_price}

    order = Order(
        user_id=account.user_id,
        strategy_id=account.strategy_id,
        paper_account_id=account.id,
        mode=TradingMode.PAPER,
        symbol=symbol,
        side=OrderSide(side),
        order_type=OrderType(order_type if order_type in ("market", "limit") else "market"),
        quantity=quantity,
        price=float(actionable.params.get("limit_price") or current_price),
        status=OrderStatus.PENDING,
    )
    db.add(order)
    await db.flush()

    from app.paper_trading.service import settle_order
    from app.paper_trading.portfolio import list_open_positions
    try:
        trade = await settle_order(db, order.id, account.user_id, current_price)
    except AppError as exc:
        if exc.code != "LIMIT_NOT_REACHED":
            raise
        await db.commit()
        return {"signal": None, "order": {"order_id": order.id, "status": "pending"}, "price": current_price}
    positions = await list_open_positions(db, account)
    for position in positions:
        position.last_mark_price = current_price
        for signal in signals:
            percent = float(signal.params.get("percent", 0)) / 100
            if signal.action == "set_stop_loss":
                position.stop_loss = float(position.average_entry_price) * (1 - percent)
            if signal.action == "set_take_profit":
                position.take_profit = float(position.average_entry_price) * (1 + percent)
    await db.commit()
    fill = {"executed_price": float(trade.executed_price), "executed_quantity": float(trade.executed_quantity), "fee": float(trade.fee), "pnl": float(trade.pnl) if trade.pnl is not None else None}
    portfolio_state = {"cash_balance": float(account.balance)}
    from app.redis.pubsub import publish_user_event
    await publish_user_event(account.user_id, "paper_order", {"order_id": order.id, "symbol": symbol, **fill})
    await publish_user_event(account.user_id, "portfolio_update", portfolio_state)

    logger.info("Paper trade executed: %s %s %s at %s", side, quantity, symbol, current_price)
    return {
        "signal": {"node_id": actionable.node_id, "action": actionable.action, "params": actionable.params},
        "order": {"order_id": order.id, "status": order.status.value},
        "fill": fill,
        "price": current_price,
        "account": portfolio_state,
    }
