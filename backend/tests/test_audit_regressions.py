"""Execution and security edge cases found in the October project audit."""
from types import SimpleNamespace
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select

from app.core.exceptions import AppError
from app.database.models.paper_trading import PaperAccount, Order
from app.market_data.historical import normalize_ohlcv
from app.strategy_engine.conditions import crosses_above, crosses_below, logical_not
from app.strategy_engine.executor import Signal
from app.backtesting.simulator import simulate_strategy_on_ohlcv
from tests.test_safety_regressions import graph_with
from tests.test_paper_simulation import saved_graph, start, candles, get
from tests.test_futures_demo import activate, FakeDemo


@pytest.fixture(autouse=True)
def reset_demo_adapter():
    FakeDemo.calls = []
    FakeDemo.queries = {}
    from decimal import Decimal
    FakeDemo.qty = Decimal(0)
    FakeDemo.fail_entry = FakeDemo.fail_protection = False


@pytest.mark.parametrize('cross', [crosses_above, crosses_below])
def test_crossovers_preserve_unknown_under_not(cross):
    output = cross(np.array([np.nan, 1, 2]), np.array([1, 2, 1]))
    assert pd.isna(output.iloc[0]) and pd.isna(output.iloc[1])
    assert pd.isna(logical_not(output).iloc[1])
    assert cross(None, np.array([1, 2])).empty


def test_bad_candle_bounds_are_rejected():
    with pytest.raises(ValueError, match='high/low'):
        normalize_ohlcv([[1700000000000, 100, 90, 80, 100, 1]])


@pytest.mark.asyncio
@pytest.mark.parametrize('market,actions', [('spot', ['buy', 'sell']), ('futures', ['openLong', 'openShort'])])
async def test_paper_conflicting_signals_do_not_create_orders(client, auth_headers, monkeypatch, db_session, market, actions):
    strategy = await saved_graph(client, auth_headers, actions[0])
    account = await start(client, auth_headers, strategy, market=market)
    async def fetch(**kwargs): return candles()
    monkeypatch.setattr('app.paper_trading.engine.fetch_futures_ohlcv', fetch)
    monkeypatch.setattr('app.paper_trading.engine.fetch_latest_ohlcv', fetch)
    monkeypatch.setattr('app.strategy_engine.executor.StrategyExecutor.evaluate',
        lambda *args, **kwargs: [Signal(str(i), action, {'amount': 1}) for i, action in enumerate(actions)])
    response = await client.post('/api/paper-trading/tick', headers=auth_headers, json={'paper_account_id': account['id']})
    assert response.status_code == 200, response.text
    updated = await get(client, auth_headers, 'account', account['id'])
    assert updated['diagnostics']['reason_code'] == 'CONFLICTING_SIGNALS'
    assert await db_session.scalar(select(Order.id).where(Order.paper_account_id == account['id'])) is None


@pytest.mark.asyncio
async def test_missing_first_unprocessed_candle_blocks_tick(client, auth_headers, monkeypatch, db_session):
    strategy = await saved_graph(client, auth_headers)
    account = await start(client, auth_headers, strategy)
    frame = candles()
    previous = frame.iloc[-3].timestamp.to_pydatetime()
    row = await db_session.get(PaperAccount, account['id'])
    row.last_processed_bar = previous
    await db_session.commit()
    # Old history is present and newest bar is fresh, but the one immediately
    # following the last processed bar is absent.
    async def fetch(**kwargs): return frame.drop(frame.index[-2]).reset_index(drop=True)
    monkeypatch.setattr('app.paper_trading.engine.fetch_futures_ohlcv', fetch)
    response = await client.post('/api/paper-trading/tick', headers=auth_headers, json={'paper_account_id': account['id']})
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'CANDLE_HISTORY_GAP'
    assert await db_session.scalar(select(Order.id).where(Order.paper_account_id == account['id'])) is None


def test_partial_backtest_sell_allocates_fees_and_slippage(monkeypatch):
    frame = candles().iloc[-3:].copy()
    def evaluate(self, context, **kwargs):
        count = len(context['candles'])
        if count == 1: return [Signal('buy', 'buy', {'amount': 2})]
        if count == 2: return [Signal('sell', 'sell', {'amount': .5})]
        return []
    monkeypatch.setattr('app.strategy_engine.executor.StrategyExecutor.evaluate', evaluate)
    result = simulate_strategy_on_ohlcv(graph_with(), frame, symbol='BTC/USDT', timeframe='1h',
        starting_capital=1000, fees_pct=.001, slippage_pct=.01)
    trades = result['trade_history']
    assert [t['quantity'] for t in trades] == [2, .5, 1.5]
    assert [t['price'] for t in trades] == [101, 99, 99]
    assert sum(t['pnl'] or 0 for t in trades) == pytest.approx(-4.4)
    assert result['metrics']['final_portfolio_value'] == pytest.approx(995.6)


def test_backtest_protection_is_independent_of_signal_order(monkeypatch):
    def evaluate(self, context, **kwargs):
        if len(context['candles']) != 1: return []
        return [Signal('risk', 'set_stop_loss', {'percent': .5}), Signal('buy', 'buy', {'amount': 1})]
    monkeypatch.setattr('app.strategy_engine.executor.StrategyExecutor.evaluate', evaluate)
    result = simulate_strategy_on_ohlcv(graph_with(), candles().iloc[-2:], symbol='BTC/USDT', timeframe='1h',
        starting_capital=1000, fees_pct=0, slippage_pct=0)
    assert result['trade_history'][-1]['price'] == 99.5


@pytest.mark.asyncio
async def test_delete_strategy_preserves_pinned_paper_algorithm(client, auth_headers):
    strategy = await saved_graph(client, auth_headers)
    await start(client, auth_headers, strategy)
    response = await client.delete('/api/strategies/' + strategy, headers=auth_headers)
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'STRATEGY_IN_USE'
    assert (await client.get('/api/strategies/' + strategy, headers=auth_headers)).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', [{}, {'dualSidePosition': None}, {'dualSidePosition': 'false'}])
async def test_demo_requires_explicit_account_mode(monkeypatch, mode):
    from app.futures.service import verify_connection
    class UnknownMode(FakeDemo):
        async def request(self, method, path, params=None, signed=False):
            if path.endswith('/positionSide/dual'): return mode
            return await super().request(method, path, params, signed)
    with pytest.raises(AppError, match='one-way'):
        await verify_connection(UnknownMode(SimpleNamespace(is_testnet=True)))


@pytest.mark.asyncio
async def test_unrecognized_protection_state_flattens_demo(client, auth_headers, monkeypatch):
    session, _ = await activate(client, auth_headers, monkeypatch)
    original = FakeDemo.order
    async def order(self, params, conditional=False):
        result = await original(self, params, conditional)
        if conditional: result['algoStatus'] = 'FINISHED'
        return result
    monkeypatch.setattr(FakeDemo, 'order', order)
    response = await client.post(f"/api/futures-demo/sessions/{session['id']}/tick", headers=auth_headers)
    assert response.status_code == 409
    assert FakeDemo.qty == 0
    assert response.json()['error']['code'] == 'DEMO_PROTECTION_FAILED'


@pytest.mark.asyncio
async def test_unverifiable_protection_cannot_stay_new(client, auth_headers, monkeypatch):
    session, _ = await activate(client, auth_headers, monkeypatch)
    url = f"/api/futures-demo/sessions/{session['id']}/tick"
    assert (await client.post(url, headers=auth_headers)).status_code == 200
    from app.futures.binance_demo import DemoRequestError
    original = FakeDemo.query
    async def query(self, symbol, client_id, conditional=False):
        if conditional: raise DemoRequestError()
        return await original(self, symbol, client_id, conditional)
    monkeypatch.setattr(FakeDemo, 'query', query)
    response = await client.post(url, headers=auth_headers)
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'DEMO_RECONCILIATION_REQUIRED'
    assert len([call for call in FakeDemo.calls if 'newClientOrderId' in call]) == 1


@pytest.mark.asyncio
async def test_account_responses_are_not_cached(client, auth_headers):
    response = await client.get('/api/users/me', headers=auth_headers)
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'


def test_graph_coordinates_reject_nonfinite_values():
    from pydantic import ValidationError
    from app.schemas.strategy import StrategyGraph
    wire = graph_with().model_dump(by_alias=True)
    wire['nodes'][0]['position']['x'] = float('nan')
    with pytest.raises(ValidationError):
        StrategyGraph.model_validate(wire)


def _protected_routes():
    from app.main import app
    public = {'/api/auth/register', '/api/auth/login', '/api/auth/forgot-password', '/api/auth/reset-password',
        '/api/auth/browser/register', '/api/auth/browser/login'}
    routes = [(method.upper(), path) for path, operations in app.openapi()['paths'].items()
        if path.startswith('/api/') and path not in public for method in operations
        if method in {'get', 'post', 'put', 'delete', 'patch'}]
    assert len(routes) >= 30
    return routes


@pytest.mark.asyncio
@pytest.mark.parametrize('method,path', _protected_routes())
async def test_every_private_http_route_requires_authentication(client, method, path):
    import re
    path = re.sub(r'\{[^}]+\}', 'unknown', path)
    response = await client.request(method, path, json={} if method in {'POST', 'PUT', 'PATCH'} else None)
    assert response.status_code == 401, (method, path, response.text)


@pytest.mark.asyncio
async def test_paper_worker_continues_after_one_account_failure(client, auth_headers, monkeypatch):
    from app.paper_trading import worker
    from tests.conftest import TestSessionLocal
    strategy = await saved_graph(client, auth_headers)
    first = await start(client, auth_headers, strategy)
    second = await start(client, auth_headers, strategy)
    monkeypatch.setattr(worker, 'AsyncSessionLocal', TestSessionLocal)
    checked = []
    async def tick(db, account, graph, symbol, timeframe):
        checked.append(account.id)
        if account.id == first['id']:
            raise AppError('TEST_OUTAGE', 'Public market data unavailable', 503)
    monkeypatch.setattr(worker, 'run_paper_trading_tick', tick)
    await worker.run_once()
    assert set(checked) == {first['id'], second['id']}
    row = await get(client, auth_headers, 'account', first['id'])
    assert row['diagnostics']['reason_code'] == 'TEST_OUTAGE'
    await client.post('/api/paper-trading/stop', headers=auth_headers, json={'paper_account_id': first['id']})
    checked.clear()
    await worker.run_once()
    assert checked == [second['id']]


@pytest.mark.asyncio
async def test_demo_worker_only_processes_running_sessions(client, auth_headers, monkeypatch, db_session):
    from app.futures import worker
    from app.database.models.futures import DemoSession
    from tests.conftest import TestSessionLocal
    session, _ = await activate(client, auth_headers, monkeypatch)
    monkeypatch.setattr(worker, 'AsyncSessionLocal', TestSessionLocal)
    checked = []
    async def tick(db, row):
        checked.append(row.id)
        raise AppError('TEST_OUTAGE', 'Unavailable', 503)
    monkeypatch.setattr(worker, 'run_tick', tick)
    await worker.run_once()
    assert checked == [session['id']]
    row = await db_session.get(DemoSession, session['id'])
    row.status = 'paused'
    await db_session.commit()
    checked.clear()
    await worker.run_once()
    assert checked == []


@pytest.mark.parametrize('kind,params,expected', [('movingAverage', {'period':500},502),
    ('macd', {'slow':500,'fast':12,'signal':200,'output':'histogram'},701), ('rsi', {'period':200},203)])
def test_long_periods_request_enough_history(kind, params, expected):
    from app.strategy_engine.history import candle_limit
    from app.strategy_engine.executor import StrategyExecutor
    from tests.test_strategy_engine.test_executor import make_dummy_candles
    graph = graph_with(kind)
    graph.nodes[0].data.params = params
    assert candle_limit(graph) == expected
    trace = []
    # Drop the exchange's unfinished bar: both closed observations must still
    # be usable by conditions/crossovers at the maximum supported periods.
    signals = StrategyExecutor(graph).evaluate({'candles': make_dummy_candles(expected - 1)}, trace=trace)
    assert signals
    assert trace[0]['current'] is not None and trace[0]['previous'] is not None


def test_backtest_conflicting_actions_never_trade(monkeypatch):
    monkeypatch.setattr('app.strategy_engine.executor.StrategyExecutor.evaluate',
        lambda *args, **kwargs: [Signal('buy','buy',{'amount':1}), Signal('sell','sell',{'amount':1})])
    result = simulate_strategy_on_ohlcv(graph_with(), candles().iloc[-3:], symbol='BTC/USDT', timeframe='1h',
        starting_capital=1000, fees_pct=.001, slippage_pct=.01)
    assert result['trade_history'] == []
    assert result['metrics']['final_portfolio_value'] == 1000


@pytest.mark.asyncio
async def test_client_selected_fill_prices_disabled_outside_development(client, auth_headers, monkeypatch):
    from app.core.config import get_settings
    # Production now requires cookie authentication; keep proving the helper
    # itself rejects an authenticated user, rather than stopping at the auth gate.
    from tests.test_browser_sessions import register, ORIGIN
    registered = await register(client)
    raw = client.cookies.get('algoflow_session')
    csrf = registered.json()['csrf_token']
    client.cookies.clear()
    client.cookies.set('__Host-algoflow_session', raw)
    monkeypatch.setattr(get_settings(), 'environment', 'production')
    response = await client.post('/api/paper-trading/simulate-fill', headers={**ORIGIN, 'X-CSRF-Token':csrf},
        json={'order_id':'unused','current_price':1})
    assert response.status_code == 403
    assert response.json()['error']['code'] == 'SIMULATION_HELPER_DISABLED'
