"""Persist-before-send order ledger. No network transport or API activation.

All production callers must hold account_lock and pass a fresh Guard. Once an
intent reaches SENDING it is never sent again, even if the exchange cannot
find it. Recovery observes the persisted client ID instead of resubmitting.
"""
import hashlib
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sqlalchemy import select, text

from app.core.exceptions import AppError
from app.database.models.live import LiveAccount, LiveRun, LiveOrder, LiveEvent

UNSETTLED = {'SENDING', 'UNKNOWN', 'NEW', 'PARTIALLY_FILLED', 'TRIGGERED'}
TERMINAL = {'FILLED', 'CANCELED', 'EXPIRED', 'REJECTED', 'ABANDONED'}


@dataclass(frozen=True)
class Guard:
    account_id: str
    token: str


class SubmissionFailure(Exception):
    def __init__(self, ambiguous=True):
        self.ambiguous = ambiguous


async def assert_guard(db, guard):
    account = await db.scalar(select(LiveAccount).where(LiveAccount.id == guard.account_id)
        .with_for_update().execution_options(populate_existing=True))
    if account is None or account.fence_token != guard.token:
        raise AppError('LIVE_WORKER_REPLACED', 'Account ownership changed; this worker must stop.', 409)
    return account


@asynccontextmanager
async def account_lock(account_id, engine, sessions):
    """Dedicated PostgreSQL advisory connection survives ledger commits.

    A new lock owner also rotates the persisted token. Any stale process must
    pass the database guard before its next intent/send; an in-flight write
    remains SENDING and blocks replacement entry until reconciled.
    """
    if engine.dialect.name != 'postgresql':
        raise AppError('LIVE_POSTGRES_REQUIRED', 'Live account coordination requires PostgreSQL.', 503)
    key = int.from_bytes(hashlib.sha256(account_id.encode()).digest()[:8], 'big', signed=True)
    async with engine.connect() as connection:
        locked = bool(await connection.scalar(text('SELECT pg_try_advisory_lock(:key)'), {'key': key}))
        if not locked:
            raise AppError('LIVE_ACCOUNT_BUSY', 'This account is already being reconciled.', 409)
        try:
            token = str(uuid.uuid4())
            async with sessions() as db:
                account = await db.scalar(select(LiveAccount).where(LiveAccount.id == account_id).with_for_update())
                if account is None:
                    raise AppError('LIVE_ACCOUNT_NOT_FOUND', 'Live account not found.', 404)
                account.fence_token = token
                await db.commit()
            yield Guard(account_id, token)
        finally:
            # A pooled connection must never retain a session-level advisory lock.
            try:
                await connection.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': key})
                await connection.commit()
            except BaseException:
                await connection.invalidate()
                raise


def amount(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or result > Decimal('1000000000000000'):
            raise ValueError
        return result
    except (InvalidOperation, TypeError, ValueError):
        raise AppError('LIVE_INVALID_ORDER_DATA', 'Order values must be finite and nonnegative.', 422) from None


def validate_params(run, role, params):
    base = {'symbol', 'side', 'type', 'positionSide'}
    regular = role in {'ENTRY', 'CLOSE'}
    allowed = base | ({'quantity', 'newOrderRespType'} if regular else {'algoType', 'triggerPrice', 'closePosition', 'workingType'})
    if role == 'CLOSE':
        allowed.add('reduceOnly')
    if (role not in {'ENTRY', 'CLOSE', 'STOP', 'TP'} or not isinstance(params, dict) or set(params) - allowed
            or any(not isinstance(value, str) or len(value) > 128 for value in params.values())
            or params.get('symbol') != run.symbol or params.get('side') not in {'BUY', 'SELL'}
            or params.get('positionSide') != 'BOTH'):
        raise AppError('LIVE_INVALID_ORDER', 'Order does not match the pinned run and supported order contract.', 422)
    if regular:
        if params.get('type') != 'MARKET' or amount(params.get('quantity')) <= 0 or params.get('newOrderRespType', 'RESULT') != 'RESULT':
            raise AppError('LIVE_INVALID_ORDER', 'Only positive-quantity market orders are supported.', 422)
        if role == 'CLOSE' and params.get('reduceOnly') != 'true':
            raise AppError('LIVE_REDUCE_ONLY_REQUIRED', 'Recovery closes must be reduce-only.', 422)
    elif (params.get('algoType') != 'CONDITIONAL' or params.get('closePosition') != 'true'
            or params.get('workingType') != 'MARK_PRICE' or amount(params.get('triggerPrice')) <= 0
            or params.get('type') != ('STOP_MARKET' if role == 'STOP' else 'TAKE_PROFIT_MARKET')):
        raise AppError('LIVE_INVALID_PROTECTION', 'Protection must close the position using a mark-price trigger.', 422)


def event(db, order, kind, detail=None):
    db.add(LiveEvent(account_id=order.account_id, order_id=order.id, kind=kind, detail=detail or {}))


async def prepare_intent(db, guard, run_id, role, key, params):
    account = await assert_guard(db, guard)
    run = await db.get(LiveRun, run_id, populate_existing=True)
    if run is None or run.account_id != guard.account_id or run.user_id != account.user_id:
        raise AppError('LIVE_RUN_NOT_FOUND', 'Live run not found for this account.', 404)
    validate_params(run, role, params)
    if not isinstance(key, str) or not 1 <= len(key) <= 128 or not key.isascii() or not key.isprintable():
        raise AppError('LIVE_INVALID_INTENT', 'Invalid order intent key.', 422)
    intent = run.id + ':' + role + ':' + (run.active_entry_id + ':' if role != 'ENTRY' and run.active_entry_id else '') + key
    existing = await db.scalar(select(LiveOrder).where(LiveOrder.account_id == guard.account_id, LiveOrder.intent_key == intent))
    if existing:
        if existing.cycle_entry_id != run.active_entry_id:
            raise AppError('LIVE_CYCLE_CHANGED', 'This intent belongs to a completed entry cycle.', 409)
        if existing.params != {**params, ('clientAlgoId' if role in {'STOP', 'TP'} else 'newClientOrderId'): existing.client_id}:
            raise AppError('LIVE_INTENT_CONFLICT', 'An intent cannot be reused with different parameters.', 409)
        await db.commit()
        return existing
    if role == 'ENTRY':
        unresolved = await db.scalar(select(LiveOrder.id).where(LiveOrder.account_id == guard.account_id, LiveOrder.state.in_(UNSETTLED)))
        if unresolved or run.active_entry_id:
            raise AppError('LIVE_RECONCILIATION_REQUIRED', 'Reconcile the existing cycle before another entry.', 409)
        if run.status != 'running':
            raise AppError('LIVE_ENTRIES_PAUSED', 'New entries are paused.', 409)
    else:
        entry = await db.get(LiveOrder, run.active_entry_id) if run.active_entry_id else None
        if entry is None or entry.run_id != run.id or entry.role != 'ENTRY' or amount(entry.filled_quantity) <= 0:
            raise AppError('LIVE_MANAGED_FILL_REQUIRED', 'Confirm a managed fill before protection or recovery orders.', 409)
    client_id = 'afl_' + hashlib.sha256(intent.encode()).hexdigest()[:30]
    row_id = str(uuid.uuid4())
    row = LiveOrder(id=row_id, account_id=guard.account_id, run_id=run.id, cycle_entry_id=row_id if role == 'ENTRY' else run.active_entry_id,
        client_id=client_id, intent_key=intent,
        role=role, state='READY', params={**params, ('clientAlgoId' if role in {'STOP', 'TP'} else 'newClientOrderId'): client_id})
    db.add(row)
    await db.flush()
    if role == 'ENTRY':
        run.active_entry_id = row.id
    event(db, row, 'INTENT_CREATED')
    await db.commit()
    return row


async def observe(db, order_id, result):
    """Monotonic exchange observations may be recorded after a worker is fenced.

    Recording a known response is not permission to make another network write.
    Only whitelisted response fields persist; provider errors/credentials do not.
    """
    row = await db.scalar(select(LiveOrder).where(LiveOrder.id == order_id).with_for_update().execution_options(populate_existing=True))
    if row is None:
        raise AppError('LIVE_ORDER_NOT_FOUND', 'Order not found.', 404)
    conditional = row.role in {'STOP', 'TP'}
    previous = amount(row.filled_quantity)
    state = 'UNKNOWN'
    safe = {}
    try:
        if not isinstance(result, dict):
            raise ValueError
        client = result.get('clientAlgoId' if conditional else 'clientOrderId')
        identity_key = 'algoId' if conditional else 'orderId'
        identity = result.get(identity_key)
        if client != row.client_id or not str(identity).isdigit() or int(identity) <= 0:
            raise ValueError
        if row.result and identity_key in row.result and str(row.result[identity_key]) != str(identity):
            raise ValueError
        state = str(result.get('algoStatus' if conditional else 'status', 'UNKNOWN'))
        if conditional and state == 'FINISHED':
            state = 'TRIGGERED'  # Triggering an algo does not prove the resulting order filled.
        allowed_states = ({'NEW', 'TRIGGERED', 'CANCELED', 'EXPIRED', 'REJECTED'} if conditional
            else {'NEW', 'PARTIALLY_FILLED', 'FILLED', 'CANCELED', 'EXPIRED', 'REJECTED'})
        if state not in allowed_states:
            raise ValueError
        filled = previous if conditional else amount(result.get('executedQty', '0'))
        if not conditional and (filled < previous or filled > amount(row.params['quantity'])
                or (state in {'FILLED', 'PARTIALLY_FILLED'} and filled <= 0)
                or (state == 'FILLED' and filled != amount(row.params['quantity']))):
            raise ValueError
        if (row.state in TERMINAL and (row.state == 'FILLED' or filled <= previous)
                or conditional and row.state == 'TRIGGERED' and state != 'TRIGGERED'):
            event(db, row, 'LATE_OBSERVATION_IGNORED')
            await db.commit()
            return row
        if any(isinstance(value, (list, dict)) or len(str(value)) > 128 for value in result.values()):
            raise ValueError
        if 'avgPrice' in result:
            amount(result['avgPrice'])
        safe = {key: result[key] for key in ('orderId', 'clientOrderId', 'status', 'executedQty', 'avgPrice',
            'algoId', 'clientAlgoId', 'algoStatus', 'actualOrderId') if key in result}
        if conditional and row.state == 'TRIGGERED' and row.result:
            # Repeated algo responses can omit the linked resulting order.
            safe = {**row.result, **safe}
            if row.result.get('actualOrderId'):
                safe['actualOrderId'] = row.result['actualOrderId']
        row.filled_quantity = filled
    except (ValueError, TypeError, AppError):
        # Malformed/stale data can never be treated as a successful fill.
        if row.state == 'TRIGGERED':
            event(db, row, 'INVALID_OBSERVATION_IGNORED')
            await db.commit()
            return row
        state = 'UNKNOWN'
        safe = dict(row.result or {})
    if row.state not in TERMINAL or state in TERMINAL:
        row.state = state
        row.result = safe
        event(db, row, 'ORDER_OBSERVED', {'state': state})
        await db.commit()
    else:
        await db.commit()
    return row


async def send_once(db, guard, order_id, exchange, *, entries_allowed=False):
    account = await assert_guard(db, guard)
    row = await db.get(LiveOrder, order_id, populate_existing=True)
    if row is None or row.account_id != guard.account_id:
        raise AppError('LIVE_ORDER_NOT_FOUND', 'Order not found for this account.', 404)
    run = await db.get(LiveRun, row.run_id, populate_existing=True)
    if run is None or run.account_id != guard.account_id or run.user_id != account.user_id or run.active_entry_id != row.cycle_entry_id:
        raise AppError('LIVE_CYCLE_CHANGED', 'This intent belongs to a different or completed entry cycle.', 409)
    if row.state != 'READY':
        await db.commit()
        return row
    validate_params(run, row.role, {key: value for key, value in row.params.items() if key not in {'clientAlgoId', 'newClientOrderId'}})
    if row.role == 'ENTRY' and (not entries_allowed or run.status != 'running'):
        raise AppError('LIVE_ENTRIES_PAUSED', 'New entries are disabled.', 403)
    row.state = 'SENDING'
    event(db, row, 'ORDER_SENDING')
    await db.commit()
    try:
        result = await exchange.submit(dict(row.params), conditional=row.role in {'STOP', 'TP'})
    except Exception as exc:
        # Cancellation/process death leaves SENDING durable for reconciliation.
        row = await db.scalar(select(LiveOrder).where(LiveOrder.id == order_id).with_for_update().execution_options(populate_existing=True))
        if row.state in {'SENDING', 'UNKNOWN'}:
            row.state = 'REJECTED' if isinstance(exc, SubmissionFailure) and not exc.ambiguous else 'UNKNOWN'
        event(db, row, 'SUBMISSION_UNCONFIRMED', {'state': row.state})
        await db.commit()
        raise AppError('LIVE_SUBMISSION_UNCONFIRMED', 'Order submission needs reconciliation before any further entry.', 503) from None
    return await observe(db, row.id, result)
