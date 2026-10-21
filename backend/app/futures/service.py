"""Demo-only futures orchestration with durable intent and reconciliation.

One dedicated, single-asset, one-way account per running connection. No
blind retries of submissions. Production routing does not exist here.
"""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pandas as pd
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppError
from app.database.models.exchange_connection import ExchangeConnection
from app.database.models.futures import DemoOrder, DemoSession
from app.database.models.strategy import StrategyVersion
from app.futures.binance_demo import BinanceDemo, DemoRequestError, decimal, quantize_quantity
from app.market_data.historical import TIMEFRAME_DELTA
from app.schemas.strategy import StrategyGraph
from app.strategy_engine.executor import StrategyExecutor
from app.futures.diagnostics import note, evaluation

UNRESOLVED = {'SENDING', 'UNKNOWN'}
TERMINAL = {'FILLED', 'CANCELED', 'CANCELLED', 'EXPIRED', 'REJECTED', 'FINISHED'}


def validate_demo_graph(graph):
    executor = StrategyExecutor(graph)
    nodes = graph.nodes
    for node in nodes:
        if node.data.node_type == 'sentiment':
            raise AppError('DEMO_SENTIMENT_UNAVAILABLE', 'Sentiment execution must be integrated before deploying a sentiment graph.', 422)
        if node.data.node_type in {'buy', 'sell', 'openLong', 'openShort'} and node.data.params.get('type', 'market') != 'market':
            raise AppError('DEMO_MARKET_ORDERS_ONLY', 'The demo runner currently supports market actions only.', 422)
    for kind in ('stopLoss', 'takeProfit'):
        risk = [node for node in nodes if node.data.node_type == kind]
        if len(risk) != 1 or not 0 < float(risk[0].data.params['percent']) <= 10:
            raise AppError('DEMO_RISK_REQUIRED', 'Use exactly one stop-loss and take-profit node, each greater than zero and at most 10%.', 422)
    return executor


async def verify_connection(adapter):
    account = await adapter.account()
    # Account V3 contains balances/positions, not account permissions.
    config = await adapter.request('GET', '/fapi/v1/accountConfig', signed=True)
    mode = await adapter.request('GET', '/fapi/v1/positionSide/dual', signed=True)
    multi = await adapter.request('GET', '/fapi/v1/multiAssetsMargin', signed=True)
    if mode.get('dualSidePosition') is not False or multi.get('multiAssetsMargin') is not False:
        raise AppError('DEMO_ACCOUNT_MODE', 'Use one-way position mode and single-asset USDT margin in a dedicated demo account.', 422)
    if config.get('canTrade') is False:
        raise AppError('DEMO_TRADING_UNAVAILABLE', 'Binance demo account is not enabled for trading.', 422)
    if config.get('canTrade') is not True:
        raise AppError('DEMO_TRADING_STATUS_UNKNOWN', 'Binance did not return a valid account trading status. Try verifying again.', 503)
    return account


async def create_session(db, user_id, payload):
    connection = (await db.execute(select(ExchangeConnection).where(
        ExchangeConnection.id == payload.connection_id, ExchangeConnection.user_id == user_id).with_for_update())).scalar_one_or_none()
    if not connection:
        raise AppError('CONNECTION_NOT_FOUND', 'Connection not found', 404)
    active = await db.scalar(select(DemoSession.id).where(DemoSession.connection_id == connection.id, DemoSession.status != 'stopped'))
    if active:
        raise AppError('DEMO_ALREADY_ACTIVE', 'This connection already has a demo session. Stop it first.', 409)
    from app.api.routes.strategies import _get_owned_strategy
    strategy = await _get_owned_strategy(db, payload.strategy_id, user_id)
    version = max(strategy.versions, key=lambda item: item.version_number)
    validate_demo_graph(StrategyGraph.model_validate(version.graph_json))
    adapter = BinanceDemo(connection)
    account = await verify_connection(adapter)
    if any(decimal(position.get('positionAmt', 0)) != 0 for position in account.get('positions', [])):
        raise AppError('DEMO_ACCOUNT_NOT_FLAT', 'Start with no positions in a dedicated demo account.', 409)
    for path in ('/fapi/v1/openOrders', '/fapi/v1/openAlgoOrders'):
        orders = await adapter.request('GET', path, signed=True)
        if orders:
            raise AppError('DEMO_PENDING_ORDERS', 'Remove existing regular and conditional demo orders before activation.', 409)
    await adapter.rules(payload.symbol)
    try:
        await adapter.request('POST', '/fapi/v1/marginType', {'symbol': payload.symbol, 'marginType': 'ISOLATED'}, signed=True)
    except DemoRequestError as exc:
        if exc.exchange_code != -4046:  # Already isolated.
            raise
    await adapter.request('POST', '/fapi/v1/leverage', {'symbol': payload.symbol, 'leverage': 1}, signed=True)
    equity = decimal(account['totalMarginBalance'])
    if equity <= 0 or decimal(account['availableBalance']) <= 0:
        raise AppError('DEMO_BALANCE_REQUIRED', 'Fund the demo account with virtual USDT first.', 422)
    session = DemoSession(user_id=user_id, connection_id=connection.id, strategy_version_id=version.id,
        symbol=payload.symbol, timeframe=payload.timeframe, status='running', max_notional=payload.max_notional,
        loss_limit=payload.loss_limit, starting_equity=equity, message='Demo activated; waiting for a closed candle')
    note(session, 'WAITING_FIRST_CHECK', 'Activated; the runner has not evaluated a closed candle yet.')
    db.add(session)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise AppError('DEMO_ALREADY_ACTIVE', 'A demo session was activated concurrently.', 409) from None
    return session


async def acquire_lease(db, session_id):
    owner = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    result = await db.execute(update(DemoSession).where(DemoSession.id == session_id,
        or_(DemoSession.lease_until.is_(None), DemoSession.lease_until < now)).values(
        lease_owner=owner, lease_until=now + timedelta(minutes=15)))
    await db.commit()
    if result.rowcount != 1:
        raise AppError('DEMO_BUSY', 'This demo session is already processing.', 409)
    return owner


def summarize(result):
    keys = {'orderId', 'clientOrderId', 'status', 'executedQty', 'avgPrice', 'algoId', 'clientAlgoId', 'algoStatus', 'actualOrderId'}
    return {key: result[key] for key in keys if key in result}


async def reconcile(db, adapter, session):
    orders = list((await db.execute(select(DemoOrder).where(DemoOrder.session_id == session.id))).scalars())
    for order in orders:
        if order.state == 'READY' and order.role in {'ENTRY', 'CLOSE'}:
            # Crash before the first submission: abandon the stale intent.
            order.state = 'REJECTED'
            await db.commit()
        if order.state in TERMINAL or order.state == 'READY':
            continue
        try:
            result = await adapter.query(session.symbol, order.client_id, order.role in {'STOP', 'TP'})
            order.result = summarize(result)
            order.state = str(result.get('status', result.get('algoStatus', 'UNKNOWN')))
            await db.commit()
        except DemoRequestError:
            # Not found is NOT permission to blindly resubmit an unknown order.
            order.state = 'UNKNOWN'
            await db.commit()
    if any(order.state in UNRESOLVED for order in orders):
        raise AppError('DEMO_RECONCILIATION_REQUIRED', 'An order outcome is unknown. Reconcile before any further entry.', 409)
    return orders


async def submit(db, adapter, session, role, key, params):
    client_id = 'af_' + hashlib.sha256(f'{session.id}:{key}:{role}'.encode()).hexdigest()[:30]
    order = await db.scalar(select(DemoOrder).where(DemoOrder.client_id == client_id))
    if order is None:
        conditional = role in {'STOP', 'TP'}
        params = {**params, ('clientAlgoId' if conditional else 'newClientOrderId'): client_id}
        order = DemoOrder(session_id=session.id, client_id=client_id, role=role, state='READY', params=params)
        db.add(order)
        await db.commit()
    if order.state != 'READY':
        return order
    # Commit the intent before the network write so restart cannot duplicate it.
    order.state = 'SENDING'
    await db.commit()
    try:
        result = await adapter.order({key: value for key, value in order.params.items() if not key.startswith('_')}, conditional=role in {'STOP', 'TP'})
        order.result = summarize(result)
        order.state = str(result.get('status', result.get('algoStatus', 'NEW')))
        await db.commit()
    except DemoRequestError as exc:
        order.state = 'UNKNOWN' if exc.ambiguous else 'REJECTED'
        await db.commit()
        raise
    return order


async def position(adapter, session):
    rows = await adapter.positions(session.symbol)
    relevant = [row for row in rows if row.get('symbol') == session.symbol]
    if any(row.get('positionSide', 'BOTH') != 'BOTH' for row in relevant):
        raise AppError('DEMO_ACCOUNT_MODE', 'One-way position mode is required.', 422)
    row = next((row for row in relevant if decimal(row.get('positionAmt', 0)) != 0), None)
    return row, decimal(row['positionAmt']) if row else decimal(0)


async def cleanup_protection(db, adapter, session, orders):
    for order in orders:
        if order.role in {'STOP', 'TP'} and order.state not in TERMINAL and order.state != 'READY':
            await adapter.cancel(session.symbol, order.client_id)
            order.state = 'CANCELED'
            await db.commit()


async def flatten(db, adapter, session, orders, key):
    row, qty = await position(adapter, session)
    if qty:
        close = await submit(db, adapter, session, 'CLOSE', key, {'symbol': session.symbol,
            'side': 'SELL' if qty > 0 else 'BUY', 'type': 'MARKET', 'quantity': str(abs(qty)),
            'positionSide': 'BOTH', 'reduceOnly': 'true', 'newOrderRespType': 'RESULT'})
        if close.state != 'FILLED':
            raise AppError('DEMO_CLOSE_PENDING', 'Close order is not confirmed filled; protection has been retained.', 409)
        _, remaining = await position(adapter, session)
        if remaining:
            raise AppError('DEMO_CLOSE_PENDING', 'Position remains open; reconcile it before continuing.', 409)
    note(session, 'POSITION_FLAT', 'Demo position confirmed flat; reconciling protective orders.', position={'quantity': '0', 'side': 'flat'})
    await cleanup_protection(db, adapter, session, orders)


async def protect(db, adapter, session, entry, row):
    risk = entry.params.get('_risk')
    if not risk:
        raise AppError('DEMO_MISSING_RISK', 'Persisted entry has no protective levels.', 409)
    # Internal metadata must never be sent to Binance.
    qty = decimal(row['positionAmt'])
    price = decimal(row['entryPrice'])
    rules = await adapter.rules(session.symbol)
    tick = decimal(rules['PRICE_FILTER']['tickSize'])
    for role, percent in [('STOP', risk['stop']), ('TP', risk['profit'])]:
        direction = -1 if (qty > 0) == (role == 'STOP') else 1
        trigger = price * (1 + decimal(direction) * decimal(percent) / 100)
        trigger = (trigger / tick).to_integral_value() * tick
        if trigger <= 0:
            raise AppError('DEMO_INVALID_PROTECTION', 'Protective price is invalid.', 422)
        order = await submit(db, adapter, session, role, entry.client_id,
            {'algoType': 'CONDITIONAL', 'symbol': session.symbol, 'side': 'SELL' if qty > 0 else 'BUY',
             'type': 'STOP_MARKET' if role == 'STOP' else 'TAKE_PROFIT_MARKET', 'triggerPrice': str(trigger),
             'closePosition': 'true', 'positionSide': 'BOTH', 'workingType': 'MARK_PRICE'})
        if order.state != 'NEW':
            raise AppError('DEMO_PROTECTION_FAILED', 'Protection could not be confirmed; close the demo position.', 409)


async def run_tick(db, session, stop=False, resume=False):
    owner = await acquire_lease(db, session.id)
    try:
        await db.refresh(session)
        if session.status == 'stopped':
            return session
        if stop:
            session.status = 'paused'
            session.message = 'Stopping: entries disabled, reconciling and closing demo exposure'
            await db.commit()
        connection = await db.get(ExchangeConnection, session.connection_id)
        adapter = BinanceDemo(connection)
        orders = await reconcile(db, adapter, session)
        row, qty = await position(adapter, session)
        note(session, 'RECONCILED', 'Account and order reconciliation completed.',
            position={'quantity': str(qty), 'side': 'long' if qty > 0 else 'short' if qty < 0 else 'flat'})
        entries = [order for order in orders if order.role == 'ENTRY' and order.state in {'FILLED', 'PARTIALLY_FILLED'}]
        latest_entry = max(entries, key=lambda item: item.created_at) if entries else None
        if stop:
            for order in orders:
                if order.role in {'ENTRY', 'CLOSE'} and order.state not in TERMINAL:
                    await adapter.cancel_regular(session.symbol, order.client_id)
                    result = await adapter.query(session.symbol, order.client_id)
                    order.state = str(result.get('status', 'UNKNOWN'))
                    order.result = summarize(result)
                    await db.commit()
                    if order.state not in TERMINAL:
                        raise AppError('DEMO_CANCEL_PENDING', 'A market order is still pending; reconcile before stopping.', 409)
            await flatten(db, adapter, session, orders, 'stop:' + (latest_entry.client_id if latest_entry else 'flat'))
            session.status = 'stopped'
            session.message = 'Stopped; demo position flat and protection canceled'
            note(session, 'STOPPED', session.message, position={'quantity': '0', 'side': 'flat'})
            await db.commit()
            return session
        if qty and latest_entry is None:
            raise AppError('DEMO_EXTERNAL_POSITION', 'An unmanaged position exists; entries paused. Use Stop & Close.', 409)
        if qty:
            try:
                await protect(db, adapter, session, latest_entry, row)
            except AppError:
                all_orders = list((await db.execute(select(DemoOrder).where(DemoOrder.session_id == session.id))).scalars())
                await flatten(db, adapter, session, all_orders, 'protection-failure:' + latest_entry.client_id)
                raise AppError('DEMO_PROTECTION_FAILED', 'Protection failed; demo position closed and session paused.', 409) from None
        else:
            await cleanup_protection(db, adapter, session, orders)
        if any(order.role in {'ENTRY', 'CLOSE'} and order.state not in TERMINAL for order in orders):
            raise AppError('DEMO_MARKET_PENDING', 'A market order is pending or partially filled; entry paused until reconciliation.', 409)
        if session.status != 'running':
            if resume:
                account = await verify_connection(adapter)
                if decimal(account['totalMarginBalance']) <= decimal(session.starting_equity) - decimal(session.loss_limit):
                    raise AppError('DEMO_LOSS_LIMIT', 'Session loss limit remains exceeded; stop this session.', 409)
                session.status = 'running'
                session.message = 'Resumed by user after reconciliation'
                note(session, 'RESUMED_WAITING_CHECK', 'Resumed; the next runner tick will evaluate entry conditions.', last_error=None)
                await db.commit()
            if not resume:
                note(session, 'SESSION_PAUSED', 'Entries are disabled while the session is paused. Resolve the last error before resuming.')
                await db.commit()
            return session
        account = await verify_connection(adapter)
        if any(item.get('symbol') != session.symbol and decimal(item.get('positionAmt', 0)) != 0
               for item in account.get('positions', [])):
            raise AppError('DEMO_EXTERNAL_POSITION', 'Another contract has exposure in this demo account; entries paused.', 409)
        if decimal(account['totalMarginBalance']) <= decimal(session.starting_equity) - decimal(session.loss_limit):
            await flatten(db, adapter, session, orders, 'loss:' + (latest_entry.client_id if latest_entry else 'flat'))
            session.status = 'paused'
            session.message = 'Session loss limit reached; demo position closed'
            note(session, 'LOSS_LIMIT_REACHED', session.message, position={'quantity': '0', 'side': 'flat'})
            await db.commit()
            return session
        raw = await adapter.request('GET', '/fapi/v1/klines', {'symbol': session.symbol, 'interval': session.timeframe, 'limit': 1000})
        now = datetime.now(timezone.utc)
        closed = [bar for bar in raw if int(bar[6]) < int(now.timestamp() * 1000)]
        if not closed:
            raise AppError('DEMO_NO_CANDLES', 'No closed Binance demo candles available.', 503)
        if int(closed[-1][6]) < int((now - TIMEFRAME_DELTA[session.timeframe] * 2).timestamp() * 1000):
            raise AppError('DEMO_STALE_CANDLES', 'Binance demo candles are stale; entries paused.', 503)
        stamp = str(closed[-1][0])
        if session.last_bar == stamp:
            note(session, 'WAITING_NEXT_CANDLE', 'Latest closed candle already evaluated; waiting for the next candle close.')
            await db.commit()
            return session
        frame = pd.DataFrame([{'timestamp': pd.to_datetime(bar[0], unit='ms', utc=True),
            'open': float(bar[1]), 'high': float(bar[2]), 'low': float(bar[3]), 'close': float(bar[4]), 'volume': float(bar[5])} for bar in closed])
        version = await db.get(StrategyVersion, session.strategy_version_id)
        trace = []
        signals = validate_demo_graph(StrategyGraph.model_validate(version.graph_json)).evaluate({'candles': frame}, trace=trace)
        snapshot = evaluation(session, trace, signals, closed, version.version_number)
        note(session, 'CANDLE_EVALUATED', snapshot['decision'], evaluation=snapshot, last_error=None, entry_limits=None)
        session.last_bar = stamp
        session.message = 'Evaluated latest closed demo candle'
        await db.commit()
        closes = [signal for signal in signals if signal.action in {'sell', 'closePosition'}]
        opens = [signal for signal in signals if signal.action in {'buy', 'openLong', 'openShort'}]
        if qty and closes:
            await flatten(db, adapter, session, orders, stamp)
            session.message = 'Strategy closed the demo position'
            note(session, 'POSITION_CLOSED', session.message, position={'quantity': '0', 'side': 'flat'})
            await db.commit()
            return session
        if qty or not opens:
            note(session, 'POSITION_OPEN' if qty else 'NO_ENTRY_SIGNAL',
                'A position is already open; waiting for an exit or protective order. Additional entries are disabled.' if qty else 'Entry conditions did not produce a signal on the latest closed candle.')
            await db.commit()
            return session
        pending_regular = await adapter.request('GET', '/fapi/v1/openOrders', signed=True)
        if pending_regular:
            raise AppError('DEMO_PENDING_ORDERS', 'Regular orders are pending in the demo account; new entry skipped.', 409)
        if len(opens) != 1 or closes:
            raise AppError('DEMO_CONFLICTING_SIGNALS', 'Conflicting entry/exit signals; entry skipped.', 422)
        stop_signals = [signal for signal in signals if signal.action == 'set_stop_loss']
        profits = [signal for signal in signals if signal.action == 'set_take_profit']
        if len(stop_signals) != 1 or len(profits) != 1:
            raise AppError('DEMO_RISK_NOT_TRIGGERED', 'Entry must trigger stop loss and take profit together.', 422)
        rules = await adapter.rules(session.symbol)
        amount = quantize_quantity(opens[0].params['amount'], rules)
        mark = decimal((await adapter.request('GET', '/fapi/v1/premiumIndex', {'symbol': session.symbol}))['markPrice'])
        notional = amount * mark
        minimum = decimal(rules.get('MIN_NOTIONAL', {}).get('notional', 5))
        note(session, 'CHECKING_ENTRY_LIMITS', 'Entry signal produced; checking exchange and session limits.',
            entry_limits={'rounded_quantity': str(amount), 'mark_price': str(mark), 'notional': str(notional),
                'exchange_minimum_notional': str(minimum), 'maximum_notional': str(session.max_notional),
                'available_margin': str(account['availableBalance']),
                'checks': [{'label':'Exchange minimum notional', 'passed': notional >= minimum},
                    {'label':'Session notional cap', 'passed': notional <= decimal(session.max_notional)},
                    {'label':'Available demo margin including 5% buffer', 'passed': notional * decimal('1.05') <= decimal(account['availableBalance'])}]})
        if notional < minimum or notional > decimal(session.max_notional) or notional * decimal('1.05') > decimal(account['availableBalance']):
            raise AppError('DEMO_RISK_LIMIT', 'Entry violates minimum notional, session notional cap or available demo margin.', 422)
        # Refuse new entries if account settings were changed externally.
        rows = await adapter.positions(session.symbol)
        if not rows or any(str(item.get('leverage')) != '1' or item.get('marginType') != 'isolated' for item in rows):
            raise AppError('DEMO_ACCOUNT_SETTINGS', 'Restore isolated margin and 1x leverage before another entry.', 422)
        params = {'symbol': session.symbol, 'side': 'SELL' if opens[0].action == 'openShort' else 'BUY',
            'type': 'MARKET', 'quantity': str(amount), 'positionSide': 'BOTH', 'newOrderRespType': 'RESULT',
            '_risk': {'stop': stop_signals[0].params['percent'], 'profit': profits[0].params['percent']}}
        entry = await submit(db, adapter, session, 'ENTRY', stamp, params)
        if entry.state != 'FILLED':
            raise AppError('DEMO_ENTRY_PENDING', 'Entry is not confirmed filled; reconciliation required.', 409)
        row, qty = await position(adapter, session)
        if not qty:
            raise AppError('DEMO_POSITION_PENDING', 'Filled entry is not visible in positions yet; reconcile before continuing.', 409)
        note(session, 'ENTRY_POSITION_OBSERVED', 'Entry position observed; confirming stop loss and take profit.',
            position={'quantity': str(qty), 'side': 'long' if qty > 0 else 'short'})
        try:
            await protect(db, adapter, session, entry, row)
        except AppError:
            all_orders = list((await db.execute(select(DemoOrder).where(DemoOrder.session_id == session.id))).scalars())
            await flatten(db, adapter, session, all_orders, 'protection-failure:' + entry.client_id)
            raise AppError('DEMO_PROTECTION_FAILED', 'Protection failed; demo position closed and session paused.', 409) from None
        if abs(qty) * decimal(row['entryPrice']) > decimal(session.max_notional) * decimal('1.01'):
            all_orders = list((await db.execute(select(DemoOrder).where(DemoOrder.session_id == session.id))).scalars())
            await flatten(db, adapter, session, all_orders, 'fill-cap:' + entry.client_id)
            raise AppError('DEMO_FILL_RISK_LIMIT', 'Actual filled notional exceeded the cap; demo position closed.', 409)
        session.message = 'Demo entry filled with exchange-held stop loss and take profit'
        note(session, 'ENTRY_FILLED', session.message, position={'quantity': str(qty), 'side': 'long' if qty > 0 else 'short'})
        await db.commit()
        return session
    except AppError as exc:
        observed = session.diagnostics
        await db.rollback()
        await db.refresh(session)
        session.status = 'needs_attention'
        session.message = exc.message[:255]
        session.diagnostics = observed
        note(session, exc.code, exc.message, last_error={'code': exc.code, 'message': exc.message, 'at': datetime.now(timezone.utc).isoformat()})
        await db.commit()
        raise
    except Exception:
        await db.rollback()
        await db.refresh(session)
        session.status = 'needs_attention'
        session.message = 'Unexpected demo failure. Reconcile account and orders before continuing.'
        note(session, 'DEMO_NEEDS_ATTENTION', session.message, last_error={'code':'DEMO_NEEDS_ATTENTION', 'message': session.message})
        await db.commit()
        raise AppError('DEMO_NEEDS_ATTENTION', session.message, 503) from None
    finally:
        await db.execute(update(DemoSession).where(DemoSession.id == session.id, DemoSession.lease_owner == owner)
            .values(lease_owner=None, lease_until=None))
        await db.commit()
