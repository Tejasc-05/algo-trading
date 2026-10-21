import asyncio
from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.auth.account_security import verify_email
from app.auth.password_reset import complete_reset
from app.auth.sessions import digest
from app.core.exceptions import AppError
from app.core.security import encrypt_secret
from app.database.database import AsyncSessionLocal
from app.database.models.account_security import AccountSecurity, EmailVerificationToken
from app.database.models.password_reset import PasswordResetToken
from app.database.models.user import User

pytestmark = pytest.mark.asyncio
ORIGIN = {'Origin': 'http://localhost:5173'}


async def owner(client):
    result = await client.post('/api/auth/browser/register', headers=ORIGIN,
        json={'email': 'postgres-owner@example.com', 'password': 'password123'})
    assert result.status_code == 201, result.text
    return result.json()['user']['id']


async def test_postgres_mfa_counter_cannot_be_consumed_concurrently(client):
    user_id = await owner(client)
    secret = pyotp.random_base32()
    async with AsyncSessionLocal() as db:
        db.add(AccountSecurity(user_id=user_id, mfa_secret_encrypted=encrypt_secret(secret)))
        await db.commit()
    async def login():
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as other:
            response = await other.post('/api/auth/browser/login', headers=ORIGIN,
                json={'email':'postgres-owner@example.com', 'password':'password123', 'totp_code':pyotp.TOTP(secret).now()})
            return response.status_code
    assert sorted(await asyncio.gather(login(), login())) == [200, 401]


async def test_postgres_reset_consumed_once_and_revokes_browser(client):
    user_id = await owner(client)
    now = datetime.now(timezone.utc)
    token = 'p' * 43
    async with AsyncSessionLocal() as db:
        db.add(PasswordResetToken(token_hash=digest(token), user_id=user_id, auth_version=0,
            created_at=now, expires_at=now+timedelta(minutes=10)))
        await db.commit()
    async def reset():
        async with AsyncSessionLocal() as db:
            try:
                await complete_reset(db, token, 'changed-password123')
                return 'ok'
            except AppError as exc:
                await db.rollback()
                return exc.code
    assert sorted(await asyncio.gather(reset(), reset())) == ['RESET_LINK_INVALID', 'ok']
    assert (await client.get('/api/auth/me')).status_code == 401
    async with AsyncSessionLocal() as db:
        assert (await db.get(User, user_id)).auth_version == 1


async def test_postgres_email_token_consumed_once(client):
    user_id = await owner(client)
    now = datetime.now(timezone.utc)
    token = 'e' * 43
    async with AsyncSessionLocal() as db:
        db.add(EmailVerificationToken(token_hash=digest(token), user_id=user_id, auth_version=0,
            created_at=now, expires_at=now+timedelta(minutes=10)))
        await db.commit()
    async def verify():
        async with AsyncSessionLocal() as db:
            try:
                await verify_email(db, user_id, token)
                return 'ok'
            except AppError as exc:
                await db.rollback()
                return exc.code
    assert sorted(await asyncio.gather(verify(), verify())) == ['VERIFICATION_LINK_INVALID', 'ok']


async def test_postgres_same_exchange_account_cannot_register_to_two_users(monkeypatch):
    from app.database.models.browser_session import BrowserSession
    from app.database.models.exchange_connection import ExchangeConnection
    from app.database.models.live import LiveAccount
    barrier = asyncio.Event()
    arrived = 0
    async def verified(self):
        nonlocal arrived
        arrived += 1
        if arrived == 2: barrier.set()
        await asyncio.wait_for(barrier.wait(), timeout=5)
        return {'account_identity':'f'*64, 'permissions_verified':True}
    monkeypatch.setattr('app.live.binance_readonly.BinanceReadOnly.verify', verified)
    clients = []
    try:
        prepared = []
        for i in range(2):
            client = AsyncClient(transport=ASGITransport(app=app), base_url='http://test')
            clients.append(client)
            response = await client.post('/api/auth/browser/register', headers=ORIGIN,
                json={'email':f'pg-account-{i}@example.com','password':'password123'})
            user_id=response.json()['user']['id']
            async with AsyncSessionLocal() as db:
                db.add(AccountSecurity(user_id=user_id,email_verified_at=datetime.now(timezone.utc),
                    mfa_secret_encrypted=encrypt_secret('JBSWY3DPEHPK3PXP')))
                session=await db.get(BrowserSession,digest(client.cookies.get('algoflow_session')))
                session.mfa_at=datetime.now(timezone.utc)
                connection=ExchangeConnection(user_id=user_id,exchange_name='binanceusdm',is_testnet=False,
                    is_active=True,api_key_encrypted=encrypt_secret('fake'),api_secret_encrypted=encrypt_secret('fake'))
                db.add(connection)
                await db.commit()
                prepared.append((client,connection.id,{**ORIGIN,'X-CSRF-Token':response.json()['csrf_token']}))
        responses=await asyncio.gather(*(client.post('/api/live/connections/'+connection+'/verify',headers=headers)
            for client,connection,headers in prepared))
        assert sorted(response.status_code for response in responses)==[200,409]
        account_responses=await asyncio.gather(*(client.get('/api/live/accounts') for client in clients))
        counts=sorted(len(response.json()) for response in account_responses)
        assert counts==[0,1]
        async with AsyncSessionLocal() as db:
            assert len(list((await db.execute(select(LiveAccount))).scalars()))==1
    finally:
        for client in clients: await client.aclose()


async def test_postgres_readiness_checks_current_migration_head(client):
    response=await client.get('/health/ready')
    assert response.status_code==200 and response.json()['success'] is True


async def test_password_revocation_wins_before_sensitive_live_action(client, monkeypatch):
    from app.database.models.browser_session import BrowserSession
    from app.auth import account_security
    user_id=await owner(client)
    raw=client.cookies.get('algoflow_session')
    async with AsyncSessionLocal() as db:
        db.add(AccountSecurity(user_id=user_id,email_verified_at=datetime.now(timezone.utc),
            mfa_secret_encrypted=encrypt_secret('JBSWY3DPEHPK3PXP')))
        session=await db.get(BrowserSession,digest(raw))
        session.mfa_at=datetime.now(timezone.utc)
        await db.commit()
    headers={**ORIGIN,'X-CSRF-Token':(await client.get('/api/auth/browser/session')).json()['csrf_token']}
    arrived=asyncio.Event()
    original=account_security.locked_user
    async def observed_lock(db,uid):
        arrived.set()
        return await original(db,uid)
    monkeypatch.setattr(account_security,'locked_user',observed_lock)
    async with AsyncSessionLocal() as revoker:
        user=await revoker.scalar(select(User).where(User.id==user_id).with_for_update())
        user.auth_version+=1
        pending=asyncio.create_task(client.post('/api/exchanges/connect',headers=headers,json={
            'exchange_name':'binanceusdm','api_key':'fake','api_secret':'fake','is_testnet':False}))
        await asyncio.wait_for(arrived.wait(),timeout=5)
        await revoker.commit()
        response=await pending
    assert response.status_code==401
