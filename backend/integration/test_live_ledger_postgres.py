"""Actual PostgreSQL ownership, restart and idempotency evidence."""
import asyncio

import pytest
from sqlalchemy import select

from app.core.exceptions import AppError
from app.database.database import engine, AsyncSessionLocal
from app.database.models.live import LiveAccount, LiveRun, LiveOrder
from app.database.models.strategy import Strategy, StrategyVersion
from app.live.ledger import account_lock, prepare_intent, send_once
from test_security_postgres import owner

pytestmark = pytest.mark.asyncio
PARAMS = {'symbol':'BTCUSDT','side':'BUY','type':'MARKET','quantity':'0.001','positionSide':'BOTH'}


async def setup_account(client):
    uid = await owner(client)
    async with AsyncSessionLocal() as db:
        account = LiveAccount(user_id=uid, account_identity='b'*64)
        strategy = Strategy(user_id=uid, name='PostgreSQL ledger fixture')
        db.add_all([account, strategy])
        await db.flush()
        version = StrategyVersion(strategy_id=strategy.id, version_number=1, graph_json={})
        db.add(version)
        await db.flush()
        run = LiveRun(account_id=account.id, user_id=uid, strategy_version_id=version.id,
            symbol='BTCUSDT', timeframe='1h', status='running', policy={})
        db.add(run)
        await db.commit()
        return account.id, run.id


async def test_account_coordination_rejects_concurrent_workers_and_fences_restart(client):
    account_id, run_id = await setup_account(client)
    async with account_lock(account_id, engine, AsyncSessionLocal) as original:
        with pytest.raises(AppError) as busy:
            async with account_lock(account_id, engine, AsyncSessionLocal):
                pytest.fail('A second worker acquired an occupied account.')
        assert busy.value.code == 'LIVE_ACCOUNT_BUSY'
        async with AsyncSessionLocal() as db:
            order = await prepare_intent(db, original, run_id, 'ENTRY', 'bar-1', PARAMS)
    calls = []
    class Exchange:
        async def submit(self, *args, **kwargs):
            calls.append(args)
            raise AssertionError('A replaced worker cannot reach the exchange.')
    async with account_lock(account_id, engine, AsyncSessionLocal) as replacement:
        assert replacement.token != original.token
        async with AsyncSessionLocal() as db:
            with pytest.raises(AppError) as stale:
                await send_once(db, original, order.id, Exchange(), entries_allowed=True)
            assert stale.value.code == 'LIVE_WORKER_REPLACED'
    assert calls == []


async def test_replay_releases_row_locks_before_account_lock_reacquisition(client):
    account_id, run_id = await setup_account(client)
    calls = []
    class Exchange:
        async def submit(self, params, conditional=False):
            calls.append(params)
            # A separate connection sees the committed intent BEFORE this write.
            async with AsyncSessionLocal() as observer:
                row = await observer.scalar(select(LiveOrder).where(LiveOrder.client_id == params['newClientOrderId']))
                assert row.state == 'SENDING'
            return {'orderId':123, 'clientOrderId':params['newClientOrderId'],
                'status':'FILLED', 'executedQty':'0.001'}
    async with AsyncSessionLocal() as db:
        async with account_lock(account_id, engine, AsyncSessionLocal) as guard:
            row = await prepare_intent(db, guard, run_id, 'ENTRY', 'bar-1', PARAMS)
            await prepare_intent(db, guard, run_id, 'ENTRY', 'bar-1', PARAMS)
            assert not db.in_transaction()
        async with asyncio.timeout(5):
            async with account_lock(account_id, engine, AsyncSessionLocal) as guard:
                await send_once(db, guard, row.id, Exchange(), entries_allowed=True)
                await send_once(db, guard, row.id, Exchange(), entries_allowed=True)
                assert not db.in_transaction()
        # The supplied ledger session deliberately outlives all account locks.
        async with asyncio.timeout(5):
            async with account_lock(account_id, engine, AsyncSessionLocal):
                pass
    assert len(calls) == 1


async def test_canceled_worker_releases_its_advisory_connection(client):
    account_id, _ = await setup_account(client)
    acquired = asyncio.Event()
    async def worker():
        async with account_lock(account_id, engine, AsyncSessionLocal):
            acquired.set()
            await asyncio.Event().wait()
    task = asyncio.create_task(worker())
    await asyncio.wait_for(acquired.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with asyncio.timeout(5):
        async with account_lock(account_id, engine, AsyncSessionLocal):
            pass


async def test_canceled_submission_remains_durable_and_restart_never_resends(client):
    account_id, run_id = await setup_account(client)
    sending = asyncio.Event()
    calls = []
    order_id = None
    class Exchange:
        async def submit(self, params, conditional=False):
            calls.append(params)
            sending.set()
            await asyncio.Event().wait()
    async def worker():
        nonlocal order_id
        async with account_lock(account_id, engine, AsyncSessionLocal) as guard:
            async with AsyncSessionLocal() as db:
                row = await prepare_intent(db, guard, run_id, 'ENTRY', 'bar-1', PARAMS)
                order_id = row.id
                await send_once(db, guard, row.id, Exchange(), entries_allowed=True)
    task = asyncio.create_task(worker())
    await asyncio.wait_for(sending.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with account_lock(account_id, engine, AsyncSessionLocal) as guard:
        async with AsyncSessionLocal() as db:
            row = await send_once(db, guard, order_id, Exchange(), entries_allowed=True)
            assert row.state == 'SENDING'
            with pytest.raises(AppError) as blocked:
                await prepare_intent(db, guard, run_id, 'ENTRY', 'bar-2', PARAMS)
            assert blocked.value.code == 'LIVE_RECONCILIATION_REQUIRED'
    assert len(calls) == 1


async def test_database_keeps_paused_and_unresolved_accounts_exclusive(client):
    from sqlalchemy.exc import IntegrityError
    account_id, run_id = await setup_account(client)
    async with AsyncSessionLocal() as db:
        run = await db.get(LiveRun, run_id)
        run.status = 'paused'
        await db.commit()
        db.add(LiveRun(account_id=account_id,user_id=run.user_id,strategy_version_id=run.strategy_version_id,
            symbol='ETHUSDT',timeframe='1h',status='running',policy={}))
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()
        run = await db.get(LiveRun, run_id)
        run.active_entry_id = 'unresolved-cycle'
        run.status = 'stopped'
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()
