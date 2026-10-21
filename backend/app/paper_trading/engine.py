"""Closed-candle paper execution. Every order and fill remains local."""
from datetime import datetime, timezone
from math import isfinite
from sqlalchemy import select
from app.core.exceptions import AppError
from app.database.models.enums import OrderSide, OrderStatus, OrderType, TradingMode
from app.database.models.paper_trading import Order, PaperAccount
from app.market_data.historical import fetch_latest_ohlcv, TIMEFRAME_DELTA
from app.paper_trading.market import fetch_futures_ohlcv
from app.paper_trading.portfolio import list_open_positions
from app.paper_trading.service import settle_order
from app.paper_trading.account_views import snapshot
from app.paper_trading.risk import protective_exit, liquidation_price
from app.paper_trading import futures
from app.strategy_engine.executor import StrategyExecutor
from app.strategy_engine.history import candle_limit


def note(account, code, message, *, worker_check=False, **facts):
    account.diagnostics = {**(account.diagnostics or {}), 'checked_at': datetime.now(timezone.utc).isoformat(),
        'reason_code': code, 'reason': message, **facts}
    if worker_check:
        account.diagnostics = {**account.diagnostics, 'worker_checked_at': datetime.now(timezone.utc).isoformat()}


async def record_failure(db, account_id, code, message):
    await db.rollback()
    account = (await db.execute(select(PaperAccount).where(PaperAccount.id == account_id)
        .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if account and not (code == 'ACCOUNT_INACTIVE' and not account.is_active):
        note(account, code, message, worker_check=True, last_error=message)
        await db.commit()


async def _spot_order(db, account, side, quantity, price, order_type='market', limit=None):
    order = Order(user_id=account.user_id, strategy_id=account.strategy_id, paper_account_id=account.id,
        mode=TradingMode.PAPER, symbol=account.symbol, side=OrderSide(side),
        order_type=OrderType(order_type), quantity=quantity, price=limit or price, status=OrderStatus.PENDING)
    db.add(order)
    await db.flush()
    try:
        return order, await settle_order(db, order.id, account.user_id, price)
    except AppError as exc:
        if exc.code != 'LIMIT_NOT_REACHED':
            raise
        return order, None


async def _finish(db, account, code, message, price=None, trade=None):
    note(account, code, message, worker_check=True, last_error=None)
    await snapshot(db, account)
    await db.commit()
    from app.redis.pubsub import publish_user_event
    if trade:
        await publish_user_event(account.user_id, 'paper_order', {'order_id': trade.order_id})
    await publish_user_event(account.user_id, 'portfolio_update', {'paper_account_id': account.id})
    return {'signal': None, 'order': {'order_id': trade.order_id, 'status': 'filled'} if trade else None,
        'message': message, 'price': price}


async def run_paper_trading_tick(db, account, strategy_graph, symbol, timeframe='1h'):
    import pandas as pd
    if not account.is_active:
        raise AppError('ACCOUNT_INACTIVE', 'Paper account is inactive', 409)
    delta = TIMEFRAME_DELTA.get(timeframe)
    if delta is None:
        raise AppError('INVALID_TIMEFRAME', 'Unsupported timeframe', 422)
    fetch = fetch_futures_ohlcv if account.market_type == 'futures' else fetch_latest_ohlcv
    df = await fetch(symbol=symbol, timeframe=timeframe, limit=candle_limit(strategy_graph, minimum=500))
    if df is None or df.empty:
        raise AppError('MARKET_DATA_UNAVAILABLE', 'No market data available for paper trading', 503)
    df = df[df.timestamp + delta <= pd.Timestamp.now(tz='UTC')].reset_index(drop=True)
    account = (await db.execute(select(PaperAccount).where(PaperAccount.id == account.id)
        .with_for_update().execution_options(populate_existing=True))).scalar_one()
    if not account.is_active:
        raise AppError('ACCOUNT_INACTIVE', 'Paper account is inactive', 409)
    if df.empty:
        note(account, 'WAITING_CLOSED_CANDLE', 'Waiting for a closed candle', worker_check=True, last_error=None)
        await db.commit()
        return {'signal': None, 'order': None, 'message': 'Waiting for a closed candle'}
    stamp = df.iloc[-1].timestamp.to_pydatetime()
    now = datetime.now(timezone.utc)
    if stamp + delta < now - delta * 2:
        raise AppError('STALE_MARKET_DATA', 'Market candles are stale; paper execution is waiting for fresh data.', 503)
    previous = account.last_processed_bar
    previous = previous.replace(tzinfo=timezone.utc) if previous else None
    if previous and stamp <= previous:
        note(account, 'WAITING_NEXT_CANDLE', 'Waiting for the next closed candle', worker_check=True, last_error=None)
        await db.commit()
        return {'signal': None, 'order': None, 'message': 'Candle already processed'}
    # Never guess a protective fill across missing market history.
    if previous and df.iloc[0].timestamp.to_pydatetime() > previous + delta:
        raise AppError('CANDLE_HISTORY_GAP', 'Unprocessed history exceeds the candle window; stop and close or start a new paper account.', 409)
    new = df[df.timestamp > pd.Timestamp(previous)] if previous else df.iloc[-1:]
    if previous and new.iloc[0].timestamp.to_pydatetime() != previous + delta:
        raise AppError('CANDLE_HISTORY_GAP', 'The first unprocessed candle is missing; simulated execution is paused.', 409)
    if len(new) > 1 and not (new.timestamp.diff().dropna() == delta).all():
        raise AppError('CANDLE_HISTORY_GAP', 'Market data has missing candles; simulated execution is paused.', 409)
    current_price = float(df.iloc[-1]['close'])
    positions = await list_open_positions(db, account)
    exit_trade, exit_reason = None, None
    pending_trade = None
    funding = 0.0
    for _, candle in new.iterrows():
        for position in list(positions):
            # Only inspect exposure after this position was opened. Entry occurs
            # after candle close, so the entry candle cannot trigger protection.
            bar_end = candle.timestamp.to_pydatetime() + delta
            if bar_end <= position.opened_at.replace(tzinfo=timezone.utc):
                continue
            liq = liquidation_price(position, float(account.maintenance_margin_rate), float(account.fee_rate)) if account.market_type == 'futures' else None
            hit = protective_exit(position, candle, liquidation=liq)
            if hit:
                exit_reason, price = hit
                if account.market_type == 'futures':
                    exit_trade = await futures.close_position(db, account, position, price, liquidated=exit_reason == 'LIQUIDATED')
                else:
                    _, exit_trade = await _spot_order(db, account, 'sell', float(position.quantity), price)
                positions.remove(position)
                continue
            if account.market_type == 'futures':
                funding += futures.apply_funding(account, position, bar_end, float(candle['close']))
                liq = liquidation_price(position, float(account.maintenance_margin_rate), float(account.fee_rate))
                price = float(candle['close'])
                if (price <= liq if position.side.value == 'long' else price >= liq):
                    exit_reason = 'LIQUIDATED'
                    exit_trade = await futures.close_position(db, account, position, price, liquidated=True)
                    positions.remove(position)
        # Pending spot limits can fill on a touched high/low, not just the close.
        pending = list((await db.execute(select(Order).where(Order.paper_account_id == account.id,
            Order.status == OrderStatus.PENDING))).scalars())
        for order in pending:
            if candle.timestamp.to_pydatetime() + delta <= order.created_at.replace(tzinfo=timezone.utc):
                continue
            price = float(candle['open'])
            if order.order_type == OrderType.LIMIT:
                limit = float(order.price)
                if order.side == OrderSide.BUY:
                    if float(candle['low']) > limit: continue
                    price = min(price, limit)
                else:
                    if float(candle['high']) < limit: continue
                    price = max(price, limit)
            try:
                pending_trade = await settle_order(db, order.id, account.user_id, price)
                positions = await list_open_positions(db, account)
                if order.side == OrderSide.BUY:
                    # A touched limit's intrabar ordering is unknown. Apply an
                    # adverse protective hit conservatively in that same bar.
                    for position in list(positions):
                        position.opened_at = candle.timestamp.to_pydatetime()
                        hit = protective_exit(position, candle)
                        if hit and hit[0] == 'STOP_LOSS':
                            exit_reason, exit_price = hit
                            _, exit_trade = await _spot_order(db, account, 'sell', float(position.quantity), exit_price)
                            positions.remove(position)
            except AppError as exc:
                if exc.code not in {'INSUFFICIENT_BALANCE', 'INSUFFICIENT_POSITION', 'LIMIT_NOT_REACHED'}: raise
                if exc.code != 'LIMIT_NOT_REACHED': order.status = OrderStatus.REJECTED
    account.last_processed_bar = stamp
    positions = await list_open_positions(db, account)
    for position in positions:
        position.last_mark_price = current_price
    trace = []
    signals = StrategyExecutor(strategy_graph).evaluate({'symbol': symbol, 'timeframe': timeframe,
        'candles': df, 'current_price': current_price, 'sentiment': None}, trace=trace)
    note(account, 'EVALUATED', 'Strategy evaluated', worker_check=True, evaluation={
        'candle_open': stamp.isoformat(), 'candle_close': (stamp + delta).isoformat(),
        'next_candle_close': (stamp + delta * 2).isoformat(), 'price': current_price,
        'strategy_version_id': account.strategy_version_id, 'nodes': trace,
        'signals': [{'action': s.action, 'node_id': s.node_id} for s in signals],
        'funding_payment': funding, 'market_source': df.attrs.get('source', 'Public spot candles')})
    if exit_trade:
        return await _finish(db, account, exit_reason, 'Position closed by simulated ' + exit_reason.lower().replace('_', ' '), current_price, exit_trade)
    if pending_trade:
        return await _finish(db, account, 'ORDER_FILLED', 'Queued simulated order filled; no additional strategy entry on this candle', current_price, pending_trade)
    actions = {'openLong', 'openShort', 'closePosition'} if account.market_type == 'futures' else {'buy', 'sell'}
    candidates = [s for s in signals if s.action in actions]
    # An explicit futures close can reduce existing exposure. Otherwise require
    # one unambiguous action, independent of graph node/edge insertion order.
    closing = positions and any(s.action == 'closePosition' for s in candidates)
    risk_actions = [s.action for s in signals if s.action in {'set_stop_loss', 'set_take_profit'}]
    if (len(candidates) > 1 and not closing) or len(risk_actions) != len(set(risk_actions)):
        return await _finish(db, account, 'CONFLICTING_SIGNALS', 'Multiple actions or protective levels triggered; no new strategy order submitted.', current_price)
    actionable = next((s for s in signals if s.action == 'closePosition'), None) if positions else None
    actionable = actionable or next((s for s in signals if s.action in actions), None)
    if actionable is None:
        return await _finish(db, account, 'NO_SIGNAL', 'No trading signal generated', current_price)
    if account.market_type == 'futures':
        if actionable.action == 'closePosition':
            if not positions:
                return await _finish(db, account, 'NO_POSITION', 'There is no futures position to close', current_price)
            trade = await futures.close_position(db, account, positions[0], current_price)
            return await _finish(db, account, 'POSITION_CLOSED', 'Futures position closed by strategy', current_price, trade)
        if positions:
            return await _finish(db, account, 'POSITION_OPEN', 'A futures position is already open', current_price)
        try:
            position, trade = await futures.open_position(db, account,
                'long' if actionable.action == 'openLong' else 'short', float(actionable.params.get('amount', 0.1)), current_price)
        except AppError as exc:
            if exc.code != 'INSUFFICIENT_MARGIN': raise
            return await _finish(db, account, exc.code, exc.message, current_price)
        positions = [position]
    else:
        side = actionable.action
        pending = await db.scalar(select(Order.id).where(Order.paper_account_id == account.id, Order.status == OrderStatus.PENDING).limit(1))
        if pending:
            return await _finish(db, account, 'PENDING_ORDER', 'Waiting for the existing pending order', current_price)
        if side == 'buy' and positions:
            return await _finish(db, account, 'POSITION_OPEN', 'Spot position is already open', current_price)
        amount = float(actionable.params.get('amount', 0.1))
        quantity = min(amount, max(float(account.balance) * 0.95 / current_price, 0)) if side == 'buy' else min(amount, sum(float(p.quantity) for p in positions))
        if not isfinite(quantity) or quantity <= 0:
            return await _finish(db, account, 'INSUFFICIENT_RESOURCES', 'Insufficient paper balance or held quantity', current_price)
        order_type = str(actionable.params.get('type', 'market'))
        order, trade = await _spot_order(db, account, side, quantity, current_price,
            order_type, float(actionable.params.get('limit_price') or current_price))
        if trade is None:
            order.risk_params = {('stop_loss_percent' if s.action == 'set_stop_loss' else 'take_profit_percent'): float(s.params['percent'])
                for s in signals if s.action in {'set_stop_loss', 'set_take_profit'}}
            return await _finish(db, account, 'LIMIT_PENDING', 'Limit order is waiting for its price', current_price)
        positions = await list_open_positions(db, account)
    for position in positions:
        position.last_mark_price = current_price
        direction = 1 if position.side.value == 'long' else -1
        for signal in signals:
            percent = float(signal.params.get('percent', 0)) / 100
            if signal.action == 'set_stop_loss':
                position.stop_loss = float(position.average_entry_price) * (1 - direction * percent)
            elif signal.action == 'set_take_profit':
                position.take_profit = float(position.average_entry_price) * (1 + direction * percent)
    return await _finish(db, account, 'ORDER_FILLED', 'Simulated order filled', current_price, trade)
