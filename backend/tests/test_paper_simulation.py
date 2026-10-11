"""Behavioral checks for isolation, real graph execution and virtual futures risk."""
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
import json
import pandas as pd
import pytest
from sqlalchemy import select
from app.core.exceptions import AppError
from app.database.models.paper_trading import PaperAccount, Order, Trade, PaperEquitySnapshot
from app.database.models.enums import PositionSide, OrderStatus
from app.paper_trading import futures
from app.paper_trading.account_views import account_view
from app.paper_trading.portfolio import list_open_positions
from app.paper_trading.risk import protective_exit, liquidation_price
from tests.test_api_endpoints import _create_test_strategy
from tests.test_strategy_engine.test_executor import _node, _edge


def candles(price=100):
    stamps = pd.date_range(end=pd.Timestamp.now(tz='UTC').floor('h') - pd.Timedelta(hours=1), periods=100, freq='h')
    return pd.DataFrame(dict(timestamp=stamps, open=price, high=price+1, low=price-1, close=price, volume=10))


async def saved_graph(client, headers, action='openLong', threshold=200):
    graph = dict(nodes=[_node('p', 'price'), _node('c', 'condition', {'operator':'<', 'value':threshold}),
        _node('a', action, {'amount':1, 'type':'market'}), _node('sl', 'stopLoss', {'percent':2}),
        _node('tp', 'takeProfit', {'percent':4})], edges=[_edge('1','p','c'), _edge('2','c','a'),
        _edge('3','c','sl'), _edge('4','c','tp')])
    response = await client.post('/api/strategies', headers=headers, json={'name':'Paper test', 'graph':graph})
    assert response.status_code == 201, response.text
    return response.json()['id']


async def start(client, headers, strategy, market='futures', **settings):
    response = await client.post('/api/paper-trading/start', headers=headers,
        json={'strategy_id':strategy, 'symbol':'BTC/USDT', 'market_type':market, **settings})
    assert response.status_code == 201, response.text
    return response.json()


async def get(client, headers, endpoint, id):
    response = await client.get(f'/api/paper-trading/{endpoint}?paper_account_id={id}', headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_futures_graph_runs_once_and_is_account_scoped(client, auth_headers, db_session, monkeypatch):
    strategy = await saved_graph(client, auth_headers)
    first = await start(client, auth_headers, strategy, starting_balance=1000, leverage=5)
    second = await start(client, auth_headers, strategy, starting_balance=2000)
    async def fetch(**kwargs): return candles()
    monkeypatch.setattr('app.paper_trading.engine.fetch_futures_ohlcv', fetch)
    for _ in range(2):
        r = await client.post('/api/paper-trading/tick', headers=auth_headers, json={'paper_account_id':first['id']})
        assert r.status_code == 200, r.text
    trades = await get(client, auth_headers, 'trades', first['id'])
    assert len(trades) == 1
    assert await get(client, auth_headers, 'trades', second['id']) == []
    positions = await get(client, auth_headers, 'positions', first['id'])
    assert len(positions) == 1 and positions[0]['side'] == 'long'
    assert positions[0]['margin'] == pytest.approx(20.01)
    assert positions[0]['stop_loss'] == pytest.approx(100.05 * .98)
    assert positions[0]['liquidation_price'] < positions[0]['stop_loss']
    assert await get(client, auth_headers, 'positions', second['id']) == []
    account = await get(client, auth_headers, 'account', first['id'])
    assert account['equity'] == pytest.approx(999.85, abs=.01)
    assert account['diagnostics']['reason_code'] == 'WAITING_NEXT_CANDLE'
    assert account['diagnostics']['evaluation']['nodes'][1]['current'] is True
    json.dumps(account, allow_nan=False)
    curve = await get(client, auth_headers, 'performance', first['id'])
    assert len(curve['equity_curve']) == 2
    other = await client.post('/api/auth/register', json={'email':'paper-other@example.com','password':'password123'})
    other_headers = {'Authorization':f"Bearer {other.json()['access_token']}"}
    assert (await client.get('/api/paper-trading/accounts', headers=other_headers)).json() == []
    for endpoint in ['account','positions','performance','trades']:
        r = await client.get(f"/api/paper-trading/{endpoint}?paper_account_id={first['id']}", headers=other_headers)
        assert r.status_code == 404
    for endpoint in ['stop','resume','tick']:
        assert (await client.post('/api/paper-trading/'+endpoint, headers=other_headers, json={'paper_account_id':first['id']})).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize('side,entry_price,exit_price', [('long',100,110),('short',100,90)])
async def test_futures_cash_flow_funding_and_close(db_session, client, auth_headers, side, entry_price, exit_price):
    strategy = await saved_graph(client, auth_headers, 'openShort' if side == 'short' else 'openLong')
    data = await start(client, auth_headers, strategy, starting_balance=1000, leverage=5, fee_rate=.001, slippage_rate=0)
    account = await db_session.get(PaperAccount, data['id'])
    pos, _ = await futures.open_position(db_session, account, side, 1, entry_price)
    assert float(account.balance) == pytest.approx(979.9)
    pos.last_funding_at = datetime(2026,10,10,7,0,tzinfo=timezone.utc)
    payment = futures.apply_funding(account, pos, datetime(2026,10,10,16,0,tzinfo=timezone.utc), 100)
    assert payment == pytest.approx(.02 if side == 'long' else -.02)
    assert futures.apply_funding(account, pos, datetime(2026,10,10,16,0,tzinfo=timezone.utc), 100) == 0
    pos.last_mark_price = exit_price
    before = await account_view(db_session, account)
    assert before.equity == pytest.approx(1009.9-payment)
    trade = await futures.close_position(db_session, account, pos, exit_price)
    assert float(account.balance) == pytest.approx(1010-.1-exit_price*.001-payment)
    assert float(trade.pnl) == pytest.approx(float(account.balance)-1000)
    assert await list_open_positions(db_session, account) == []


@pytest.mark.asyncio
async def test_liquidation_cannot_spend_other_free_collateral(db_session, client, auth_headers):
    strategy = await saved_graph(client, auth_headers)
    data = await start(client, auth_headers, strategy, starting_balance=1000, leverage=10, fee_rate=.001, slippage_rate=0)
    account = await db_session.get(PaperAccount, data['id'])
    pos, _ = await futures.open_position(db_session, account, 'long', 1, 100)
    threshold = liquidation_price(pos, .005, .001)
    assert threshold == pytest.approx(90/.994)
    trade = await futures.close_position(db_session, account, pos, 50, liquidated=True)
    assert float(account.balance) == pytest.approx(989.9)
    assert float(trade.pnl) == pytest.approx(-10.1)
    assert (await account_view(db_session, account)).equity == pytest.approx(989.9)


def test_ohlc_exit_ambiguity_gap_and_short_protection():
    pos = SimpleNamespace(side=PositionSide.LONG, stop_loss=98, take_profit=104)
    assert protective_exit(pos, dict(open=100, high=106, low=97)) == ('STOP_LOSS',98)
    assert protective_exit(pos, dict(open=90, high=96, low=89), liquidation=92) == ('LIQUIDATED',90)
    assert protective_exit(pos, dict(open=100, high=106, low=99)) == ('TAKE_PROFIT',104)
    pos = SimpleNamespace(side=PositionSide.SHORT, stop_loss=102, take_profit=96)
    assert protective_exit(pos, dict(open=100, high=103, low=95), liquidation=110) == ('STOP_LOSS',102)
    assert protective_exit(pos, dict(open=111, high=115, low=105), liquidation=110) == ('LIQUIDATED',111)


@pytest.mark.asyncio
async def test_stop_close_paused_spot_and_cancel_limits(client, auth_headers, db_session, monkeypatch):
    strategy = await _create_test_strategy(client, auth_headers)
    data = await start(client, auth_headers, strategy, market='spot')
    order = (await client.post('/api/paper-trading/orders', headers=auth_headers,
        json={'paper_account_id':data['id'],'symbol':'BTC/USDT','side':'buy','order_type':'market','quantity':1})).json()
    r = await client.post('/api/paper-trading/simulate-fill', headers=auth_headers,json={'order_id':order['order_id'],'current_price':100})
    assert r.status_code == 200
    pending = (await client.post('/api/paper-trading/orders',headers=auth_headers,
        json={'paper_account_id':data['id'],'symbol':'BTC/USDT','side':'buy','order_type':'limit','quantity':1,'price':50})).json()
    assert (await client.post('/api/paper-trading/stop',headers=auth_headers,json={'paper_account_id':data['id']})).status_code == 200
    assert len(await get(client,auth_headers,'positions',data['id'])) == 1
    pending_order = await db_session.get(Order,pending['order_id'])
    assert pending_order.status == OrderStatus.CANCELLED
    async def fetch(*args, **kwargs): return candles(110)
    monkeypatch.setattr('app.paper_trading.lifecycle.fetch_latest_ohlcv',fetch)
    result = await client.post('/api/paper-trading/stop',headers=auth_headers,json={'paper_account_id':data['id'],'close_positions':True})
    assert result.status_code == 200,result.text
    assert result.json()['is_active'] is False
    assert result.json()['diagnostics']['reason_code'] == 'STOPPED_FLAT'
    assert await get(client,auth_headers,'positions',data['id']) == []
    assert len(await get(client,auth_headers,'trades',data['id'])) == 2
    assert (await client.post('/api/paper-trading/resume',headers=auth_headers,json={'paper_account_id':data['id']})).json()['is_active'] is True


@pytest.mark.asyncio
async def test_engine_uses_intrabar_stop_and_never_reenters_same_candle(client,auth_headers,db_session,monkeypatch):
    strategy = await saved_graph(client,auth_headers,'buy')
    data = await start(client,auth_headers,strategy,market='spot')
    from app.paper_trading.portfolio import apply_fill_to_portfolio
    account = await db_session.get(PaperAccount,data['id'])
    await apply_fill_to_portfolio(db_session,account,symbol='BTC/USDT',side='buy',
        fill={'executed_price':100,'executed_quantity':1,'fee':0})
    pos = (await list_open_positions(db_session,account))[0]
    frame = candles()
    pos.opened_at = frame.iloc[-1].timestamp.to_pydatetime() - timedelta(hours=1)
    pos.stop_loss = 98; pos.take_profit = 104
    frame.loc[99,['high','low','close']] = [106,97,100]
    await db_session.commit()
    async def fetch(**kwargs): return frame
    monkeypatch.setattr('app.paper_trading.engine.fetch_latest_ohlcv',fetch)
    r = await client.post('/api/paper-trading/tick',headers=auth_headers,json={'paper_account_id':data['id']})
    assert r.status_code == 200,r.text
    assert await get(client,auth_headers,'positions',data['id']) == []
    assert (await get(client,auth_headers,'account',data['id']))['diagnostics']['reason_code'] == 'STOP_LOSS'
    trades = await get(client,auth_headers,'trades',data['id'])
    assert len(trades) == 1 and trades[0]['price'] == pytest.approx(98*(1-.0005))


@pytest.mark.asyncio
async def test_bad_settings_and_insufficient_margin_never_place_order(client,auth_headers,monkeypatch):
    strategy = await saved_graph(client,auth_headers)
    for settings in [{'leverage':11},{'fee_rate':-1},{'symbol':'BTC/USD'}]:
        r = await client.post('/api/paper-trading/start',headers=auth_headers,
            json={'strategy_id':strategy,'market_type':'futures','symbol':'BTC/USDT',**settings})
        assert r.status_code == 422
    data = await start(client,auth_headers,strategy,starting_balance=1)
    async def fetch(**kwargs): return candles()
    monkeypatch.setattr('app.paper_trading.engine.fetch_futures_ohlcv',fetch)
    r = await client.post('/api/paper-trading/tick',headers=auth_headers,json={'paper_account_id':data['id']})
    assert r.status_code == 200,r.text
    assert (await get(client,auth_headers,'account',data['id']))['diagnostics']['reason_code'] == 'INSUFFICIENT_MARGIN'
    assert await get(client,auth_headers,'trades',data['id']) == []
    r = await client.post('/api/paper-trading/orders',headers=auth_headers,
        json={'paper_account_id':data['id'],'symbol':'BTC/USDT','side':'sell','order_type':'market','quantity':1})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_market_failure_persists_safe_diagnostics(client,auth_headers,monkeypatch):
    strategy = await saved_graph(client,auth_headers)
    data = await start(client,auth_headers,strategy)
    async def fail(**kwargs): raise AppError('MARKET_DATA_UNAVAILABLE','Futures candles unavailable',503)
    monkeypatch.setattr('app.paper_trading.engine.fetch_futures_ohlcv',fail)
    r = await client.post('/api/paper-trading/tick',headers=auth_headers,json={'paper_account_id':data['id']})
    assert r.status_code == 503
    account = await get(client,auth_headers,'account',data['id'])
    assert account['diagnostics']['reason_code'] == 'MARKET_DATA_UNAVAILABLE'
    assert account['balance'] == 10000
    assert await get(client,auth_headers,'trades',data['id']) == []

@pytest.mark.asyncio
async def test_pending_limit_fills_on_low_and_keeps_saved_protection(client,auth_headers,db_session,monkeypatch):
    strategy = await saved_graph(client,auth_headers,'buy',threshold=0)
    data = await start(client,auth_headers,strategy,market='spot')
    response = await client.post('/api/paper-trading/orders',headers=auth_headers,
        json={'paper_account_id':data['id'],'symbol':'BTC/USDT','side':'buy','order_type':'limit','quantity':1,'price':98})
    order = await db_session.get(Order,response.json()['order_id'])
    frame = candles()
    order.created_at = frame.iloc[-1].timestamp.to_pydatetime() + timedelta(minutes=1)
    order.risk_params = {'stop_loss_percent':2,'take_profit_percent':4}
    frame.loc[99,['low','high','close']] = [97,101,100]
    await db_session.commit()
    async def fetch(**kwargs): return frame
    monkeypatch.setattr('app.paper_trading.engine.fetch_latest_ohlcv',fetch)
    response = await client.post('/api/paper-trading/tick',headers=auth_headers,json={'paper_account_id':data['id']})
    assert response.status_code == 200,response.text
    trades = await get(client,auth_headers,'trades',data['id'])
    assert len(trades) == 1 and trades[0]['price'] <= 98
    pos = (await get(client,auth_headers,'positions',data['id']))[0]
    assert pos['stop_loss'] == pytest.approx((98 + 98*.001)*.98)
    assert pos['take_profit'] == pytest.approx((98 + 98*.001)*1.04)


@pytest.mark.asyncio
async def test_stop_close_price_failure_leaves_account_and_position_intact(client,auth_headers,db_session,monkeypatch):
    strategy = await saved_graph(client,auth_headers)
    data = await start(client,auth_headers,strategy)
    account = await db_session.get(PaperAccount,data['id'])
    await futures.open_position(db_session,account,'long',1,100)
    await db_session.commit()
    before = await get(client,auth_headers,'account',data['id'])
    async def fail(*args,**kwargs): raise AppError('MARKET_DATA_UNAVAILABLE','Unavailable',503)
    monkeypatch.setattr('app.paper_trading.lifecycle.fetch_futures_ohlcv',fail)
    response = await client.post('/api/paper-trading/stop',headers=auth_headers,json={'paper_account_id':data['id'],'close_positions':True})
    assert response.status_code == 503
    after = await get(client,auth_headers,'account',data['id'])
    assert after['is_active'] is True and after['balance'] == before['balance']
    assert len(await get(client,auth_headers,'positions',data['id'])) == 1
    assert len(await get(client,auth_headers,'trades',data['id'])) == 1


@pytest.mark.asyncio
async def test_stale_candles_block_execution_without_a_fill(client,auth_headers,monkeypatch):
    strategy = await saved_graph(client,auth_headers)
    data = await start(client,auth_headers,strategy)
    async def fetch(**kwargs):
        frame = candles()
        frame.timestamp -= timedelta(days=2)
        return frame
    monkeypatch.setattr('app.paper_trading.engine.fetch_futures_ohlcv',fetch)
    response = await client.post('/api/paper-trading/tick',headers=auth_headers,json={'paper_account_id':data['id']})
    assert response.status_code == 503
    assert (await get(client,auth_headers,'account',data['id']))['diagnostics']['reason_code'] == 'STALE_MARKET_DATA'
    assert await get(client,auth_headers,'trades',data['id']) == []
