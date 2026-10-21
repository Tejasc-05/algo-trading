from types import SimpleNamespace
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient, MockTransport, Response
from sqlalchemy import select
from tests.test_browser_sessions import register, ORIGIN
from tests.test_account_security import csrf_headers

pytestmark = pytest.mark.asyncio


async def test_live_readiness_is_owned_and_cannot_be_bypassed_with_flag(client, monkeypatch):
    assert (await client.get('/api/live/readiness')).status_code == 401
    await register(client)
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), 'enable_live_trading', True)
    result = await client.get('/api/live/readiness')
    assert result.status_code == 200
    body = result.json()
    assert body['ready'] is False
    checks = {row['key']:row['passed'] for row in body['checks']}
    assert checks['email_verified'] is False and checks['mfa_enabled'] is False
    assert checks['execution_service'] is False


async def test_production_credentials_require_verified_email_mfa_and_cookie(client):
    await register(client)
    result = await client.post('/api/exchanges/connect', headers=await csrf_headers(client),
        json={'exchange_name':'binanceusdm','api_key':'fake','api_secret':'fake','is_testnet':False})
    assert result.status_code == 403
    assert result.json()['error']['code'] == 'EMAIL_VERIFICATION_REQUIRED'


async def test_read_only_binance_checks_permissions_and_never_writes():
    from app.live.binance_readonly import BinanceReadOnly
    from app.core.security import encrypt_secret
    from app.core.exceptions import AppError
    calls = []
    permissions = {'enableReading':True,'enableFutures':True,'enableWithdrawals':False,
        'ipRestrict':True,'enableInternalTransfer':False,'permitsUniversalTransfer':False,
        'enableSpotAndMarginTrading':False}
    def handler(request):
        calls.append((request.method,request.url.host,request.url.path))
        path=request.url.path
        if path.endswith('/time'): return Response(200,json={'serverTime':int(datetime.now(timezone.utc).timestamp()*1000)})
        assert request.headers['X-MBX-APIKEY'] == 'fake-key'
        assert request.url.params.get('signature')
        data = {'/sapi/v1/account/apiRestrictions':permissions,
            '/fapi/v3/balance':[{'asset':'USDT','accountAlias':'unique-account','balance':'100'}],
            '/fapi/v1/accountConfig':{'canTrade':True},
            '/fapi/v1/positionSide/dual':{'dualSidePosition':False},
            '/fapi/v1/multiAssetsMargin':{'multiAssetsMargin':False}}
        return Response(200,json=data[path])
    connection = SimpleNamespace(exchange_name='binanceusdm',is_testnet=False,is_active=True,
        api_key_encrypted=encrypt_secret('fake-key'),api_secret_encrypted=encrypt_secret('fake-secret'))
    async with AsyncClient(transport=MockTransport(handler)) as http:
        result = await BinanceReadOnly(connection,http=http).verify()
        assert len(result['account_identity']) == 64
        assert result['permissions_verified'] is True
        permissions['enableWithdrawals'] = True
        with pytest.raises(AppError) as exc:
            await BinanceReadOnly(connection,http=http).verify()
        assert exc.value.code == 'LIVE_KEY_PERMISSIONS'
    assert all(method=='GET' for method,_,_ in calls)
    assert {host for _,host,_ in calls} == {'api.binance.com','fapi.binance.com'}
    connection.is_testnet=True
    with pytest.raises(AppError): BinanceReadOnly(connection)


async def test_exchange_account_identity_unique_across_users(client, db_session, monkeypatch):
    from app.database.models.account_security import AccountSecurity
    from app.database.models.browser_session import BrowserSession
    from app.database.models.live import LiveAccount
    from app.auth.sessions import digest
    from app.core.security import encrypt_secret
    async def verified(self):
        return {'account_identity':'a'*64,'permissions_verified':True}
    monkeypatch.setattr('app.live.binance_readonly.BinanceReadOnly.verify', verified)
    async def setup(email):
        response = await register(client, email)
        uid = response.json()['user']['id']
        now=datetime.now(timezone.utc)
        db_session.add(AccountSecurity(user_id=uid,email_verified_at=now,mfa_secret_encrypted=encrypt_secret('JBSWY3DPEHPK3PXP')))
        session=await db_session.get(BrowserSession,digest(client.cookies.get('algoflow_session')))
        session.mfa_at=now
        await db_session.commit()
        headers=await csrf_headers(client)
        connection=await client.post('/api/exchanges/connect',headers=headers,json={
            'exchange_name':'binanceusdm','api_key':'fake','api_secret':'fake','is_testnet':False})
        assert connection.status_code==201, connection.text
        result=await client.post('/api/live/connections/'+connection.json()['id']+'/verify',headers=headers)
        return result,headers
    first,headers=await setup('first-live@example.com')
    assert first.status_code==200, first.text
    assert len((await client.get('/api/live/accounts')).json())==1
    await client.post('/api/auth/browser/logout',headers=headers)
    second,headers=await setup('second-live@example.com')
    assert second.status_code==409
    assert (await client.get('/api/live/accounts')).json()==[]
    assert len(list((await db_session.execute(select(LiveAccount))).scalars()))==1
