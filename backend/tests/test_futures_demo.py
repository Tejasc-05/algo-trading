import copy
import hashlib
import hmac
from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import parse_qs

import httpx
import pytest
from sqlalchemy import select

from app.core.exceptions import AppError
from app.core.security import encrypt_secret
from app.database.models.exchange_connection import ExchangeConnection
from app.database.models.futures import DemoOrder, DemoSession
from app.futures.binance_demo import BinanceDemo, DEMO_HOST, DemoRequestError, quantize_quantity
from app.futures.service import acquire_lease, submit
from tests.test_strategy_templates import TEMPLATES

pytestmark = pytest.mark.asyncio


class FakeDemo:
    fail_entry = False
    fail_protection = False
    calls = []
    queries = {}
    qty = Decimal(0)
    def __init__(self, connection):
        if not connection.is_testnet:
            raise AppError('DEMO_CONNECTION_REQUIRED', 'Demo only', 422)
    async def account(self):
        return {'canTrade': True, 'totalMarginBalance': '10000', 'availableBalance': '10000', 'positions': []}
    async def positions(self, symbol):
        return [{'symbol': symbol, 'positionAmt': str(type(self).qty), 'entryPrice': '100', 'positionSide': 'BOTH', 'leverage': '1', 'marginType': 'isolated'}]
    async def rules(self, symbol):
        return {'MARKET_LOT_SIZE': {'stepSize':'0.001','minQty':'0.001','maxQty':'100'}, 'PRICE_FILTER':{'tickSize':'0.01'},'MIN_NOTIONAL':{'notional':'5'}}
    async def request(self, method, path, params=None, signed=False):
        if path.endswith('/positionSide/dual'): return {'dualSidePosition':False}
        if path.endswith('/multiAssetsMargin'): return {'multiAssetsMargin':False}
        if path.endswith('/openOrders') or path.endswith('/openAlgoOrders'): return []
        if path.endswith('/premiumIndex'): return {'markPrice':'100'}
        if path.endswith('/klines'):
            # The newest bar is unfinished and must not be consumed.
            import time
            now = int(time.time()*1000)
            return [[now-(101-i)*3600000,'100','101','99',str(100+(i%7)), '10',now-(100-i)*3600000-1] for i in range(100)] + [[now,'100','100','100','100','1',now+3600000]]
        return {}
    async def order(self, params, conditional=False):
        type(self).calls.append(params)
        if not conditional and params.get('reduceOnly') != 'true' and type(self).fail_entry:
            raise DemoRequestError(ambiguous=True)
        if conditional and type(self).fail_protection:
            raise DemoRequestError(ambiguous=False, code=-2010)
        client = params.get('clientAlgoId', params.get('newClientOrderId'))
        if conditional:
            result = {'algoId':1,'clientAlgoId':client,'algoStatus':'NEW'}
        else:
            type(self).qty = Decimal(0) if params.get('reduceOnly') == 'true' else Decimal(params['quantity']) * (-1 if params['side']=='SELL' else 1)
            result = {'orderId':1,'clientOrderId':client,'status':'FILLED','executedQty':params['quantity'],'avgPrice':'100'}
        type(self).queries[client] = result
        return result
    async def query(self, symbol, client_id, conditional=False):
        if client_id not in type(self).queries: raise DemoRequestError(code=-2013)
        return type(self).queries[client_id]
    async def cancel(self, symbol, client_id):
        type(self).queries[client_id]['algoStatus']='CANCELED'
        return {}


@pytest.fixture(autouse=True)
def reset_fake():
    FakeDemo.calls=[]; FakeDemo.queries={}; FakeDemo.qty=Decimal(0)
    FakeDemo.fail_entry=False; FakeDemo.fail_protection=False


async def activate(client, headers, monkeypatch, quantity=0.1, short=False):
    monkeypatch.setattr('app.futures.service.BinanceDemo', FakeDemo)
    graph=copy.deepcopy(TEMPLATES[1]['graph'])
    graph['nodes'][1]['data']['params']['value']=100
    graph['nodes'][3]['data']['params']['amount']=quantity
    if short:
        graph['nodes'][3]['type']=graph['nodes'][3]['data']['nodeType']='openShort'
        graph['nodes'][4]['type']=graph['nodes'][4]['data']['nodeType']='closePosition'
        graph['nodes'][4]['data']['params']={}
    saved=await client.post('/api/strategies',headers=headers,json={'name':'Futures test','graph':graph})
    connection=await client.post('/api/exchanges/connect',headers=headers,json={'exchange_name':'binanceusdm','api_key':'test','api_secret':'test','is_testnet':True})
    payload={'strategy_id':saved.json()['id'],'connection_id':connection.json()['id'],'symbol':'BTCUSDT','max_notional':250,'loss_limit':25,'confirm_demo':True}
    started=await client.post('/api/futures-demo/sessions',headers=headers,json=payload)
    assert started.status_code==201, started.text
    return started.json(), payload


@pytest.mark.parametrize('short',[False,True])
async def test_demo_entry_protection_duplicate_tick_and_stop(client,auth_headers,monkeypatch,short):
    session,_=await activate(client,auth_headers,monkeypatch,short=short)
    url=f"/api/futures-demo/sessions/{session['id']}"
    response=await client.post(url+'/tick',headers=auth_headers)
    assert response.status_code==200,response.text
    assert len(FakeDemo.calls)==3
    assert FakeDemo.calls[0]['side']==('SELL' if short else 'BUY')
    assert '_risk' not in FakeDemo.calls[0]
    assert all(p['closePosition']=='true' and p['workingType']=='MARK_PRICE' for p in FakeDemo.calls[1:])
    assert (await client.post(url+'/tick',headers=auth_headers)).status_code==200
    assert len(FakeDemo.calls)==3
    assert (await client.post(url+'/stop',headers=auth_headers)).json()['status']=='stopped'
    assert FakeDemo.calls[-1]['reduceOnly']=='true'
    assert FakeDemo.qty==0


async def test_unknown_submission_is_never_retried(client,auth_headers,monkeypatch):
    session,_=await activate(client,auth_headers,monkeypatch)
    FakeDemo.fail_entry=True
    url=f"/api/futures-demo/sessions/{session['id']}"
    assert (await client.post(url+'/tick',headers=auth_headers)).status_code==503
    assert (await client.post(url+'/tick',headers=auth_headers)).status_code==409
    assert len(FakeDemo.calls)==1
    assert (await client.get('/api/futures-demo/sessions',headers=auth_headers)).json()[0]['status']=='needs_attention'


async def test_protection_rejection_flattens_and_pauses(client,auth_headers,monkeypatch):
    session,_=await activate(client,auth_headers,monkeypatch)
    FakeDemo.fail_protection=True
    response=await client.post(f"/api/futures-demo/sessions/{session['id']}/tick",headers=auth_headers)
    assert response.status_code==409,response.text
    assert FakeDemo.qty==0
    assert FakeDemo.calls[-1]['reduceOnly']=='true'


async def test_notional_limit_blocks_before_order(client,auth_headers,monkeypatch):
    session,_=await activate(client,auth_headers,monkeypatch,quantity=5)
    response=await client.post(f"/api/futures-demo/sessions/{session['id']}/tick",headers=auth_headers)
    assert response.status_code==422
    assert FakeDemo.calls==[]


async def test_ownership_and_active_connection_uniqueness(client,auth_headers,monkeypatch,db_session):
    session,payload=await activate(client,auth_headers,monkeypatch)
    assert (await client.post('/api/futures-demo/sessions',headers=auth_headers,json=payload)).status_code==409
    other=await client.post('/api/auth/register',json={'email':'demo-other@example.com','password':'password123'})
    headers={'Authorization':'Bearer '+other.json()['access_token']}
    assert (await client.get('/api/futures-demo/sessions',headers=headers)).json()==[]
    for action in ('tick','stop','resume'):
        assert (await client.post(f"/api/futures-demo/sessions/{session['id']}/{action}",headers=headers)).status_code==404
    assert (await client.get(f"/api/futures-demo/sessions/{session['id']}/orders",headers=headers)).status_code==404
    await acquire_lease(db_session,session['id'])
    with pytest.raises(AppError): await acquire_lease(db_session,session['id'])


async def test_transport_host_signing_and_redacted_errors(monkeypatch):
    connection=SimpleNamespace(exchange_name='binanceusdm',is_testnet=True,is_active=True,
        api_key_encrypted=encrypt_secret('demo-key'),api_secret_encrypted=encrypt_secret('demo-secret'))
    original=httpx.AsyncClient
    seen=[]
    def handler(request):
        assert str(request.url).startswith(DEMO_HOST+'/')
        seen.append(request)
        if request.url.path.endswith('/time'): return httpx.Response(200,json={'serverTime':12345})
        data=parse_qs(request.content.decode())
        raw=request.content.decode().split('&signature=')[0]
        assert data['signature'][0]==hmac.new(b'demo-secret',raw.encode(),hashlib.sha256).hexdigest()
        assert request.headers['X-MBX-APIKEY']=='demo-key'
        assert 'demo-key' not in str(request.url) and 'signature' not in str(request.url)
        return httpx.Response(503,json={'msg':'demo-secret should never escape'})
    monkeypatch.setattr('app.futures.binance_demo.httpx.AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    with pytest.raises(DemoRequestError) as exc:
        await BinanceDemo(connection).order({'symbol':'BTCUSDT','side':'BUY','type':'MARKET','quantity':'0.1'})
    assert exc.value.ambiguous and 'demo-secret' not in str(exc.value)
    connection.is_testnet=False
    with pytest.raises(AppError): BinanceDemo(connection)
    assert len(seen)==2


async def test_quantity_rounding():
    assert quantize_quantity('0.1234',{'LOT_SIZE':{'stepSize':'0.001','minQty':'0.001','maxQty':'10'}})==Decimal('0.123')


async def test_ambiguous_fill_recovery_protects_before_manual_resume(client,auth_headers,monkeypatch,db_session):
    session,_=await activate(client,auth_headers,monkeypatch)
    FakeDemo.fail_entry=True
    url=f"/api/futures-demo/sessions/{session['id']}"
    await client.post(url+'/tick',headers=auth_headers)
    entry=await db_session.scalar(select(DemoOrder).where(DemoOrder.session_id==session['id'],DemoOrder.role=='ENTRY'))
    FakeDemo.queries[entry.client_id]={'status':'FILLED','executedQty':'0.1','avgPrice':'100'}
    FakeDemo.qty=Decimal('0.1')
    FakeDemo.fail_entry=False
    resumed=await client.post(url+'/resume',headers=auth_headers)
    assert resumed.status_code==200,resumed.text
    assert resumed.json()['status']=='running'
    assert len([call for call in FakeDemo.calls if 'newClientOrderId' in call])==1
    assert len([call for call in FakeDemo.calls if 'clientAlgoId' in call])==2


async def test_loss_limit_closes_position_and_blocks_resume(client,auth_headers,monkeypatch):
    session,_=await activate(client,auth_headers,monkeypatch)
    url=f"/api/futures-demo/sessions/{session['id']}"
    assert (await client.post(url+'/tick',headers=auth_headers)).status_code==200
    async def losing_account(self):
        return {'canTrade':True,'totalMarginBalance':'9900','availableBalance':'9900','positions':[]}
    monkeypatch.setattr(FakeDemo,'account',losing_account)
    paused=await client.post(url+'/tick',headers=auth_headers)
    assert paused.status_code==200 and paused.json()['status']=='paused'
    assert FakeDemo.qty==0
    assert (await client.post(url+'/resume',headers=auth_headers)).status_code==409


async def test_partial_fill_is_protected_then_requires_reconciliation(client,auth_headers,monkeypatch,db_session):
    session,_=await activate(client,auth_headers,monkeypatch)
    FakeDemo.fail_entry=True
    url=f"/api/futures-demo/sessions/{session['id']}"
    await client.post(url+'/tick',headers=auth_headers)
    entry=await db_session.scalar(select(DemoOrder).where(DemoOrder.session_id==session['id'],DemoOrder.role=='ENTRY'))
    FakeDemo.queries[entry.client_id]={'status':'PARTIALLY_FILLED','executedQty':'0.05','avgPrice':'100'}
    FakeDemo.qty=Decimal('0.05'); FakeDemo.fail_entry=False
    response=await client.post(url+'/tick',headers=auth_headers)
    assert response.status_code==409
    assert response.json()['error']['code']=='DEMO_MARKET_PENDING'
    assert len([call for call in FakeDemo.calls if 'newClientOrderId' in call])==1
    assert len([call for call in FakeDemo.calls if 'clientAlgoId' in call])==2


async def test_futures_graph_rejected_by_spot_paper(client,auth_headers,monkeypatch):
    _,payload=await activate(client,auth_headers,monkeypatch,short=True)
    response=await client.post('/api/paper-trading/start',headers=auth_headers,json={'strategy_id':payload['strategy_id'],'symbol':'BTC/USDT'})
    assert response.status_code==422
    assert response.json()['error']['code']=='FUTURES_DEMO_REQUIRED'
