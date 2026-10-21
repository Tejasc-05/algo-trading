"""Browser auth must not leave a reusable bearer token in JavaScript storage."""
import pytest
from sqlalchemy import select

ORIGIN = {'Origin': 'http://localhost:5173'}


async def register(client, email='browser@example.com'):
    return await client.post('/api/auth/browser/register', headers=ORIGIN,
        json={'email': email, 'password': 'password123'})


@pytest.mark.asyncio
async def test_browser_cookie_session_csrf_and_logout(client):
    response = await register(client)
    assert response.status_code == 201, response.text
    assert 'access_token' not in response.json()
    cookie = response.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=strict' in cookie and 'path=/' in cookie
    csrf = response.json()['csrf_token']
    assert (await client.get('/api/auth/me')).status_code == 200
    assert (await client.get('/api/auth/browser/session')).json()['csrf_token'] == csrf
    assert (await client.post('/api/auth/browser/logout', headers=ORIGIN)).status_code == 403
    assert (await client.post('/api/auth/browser/logout', headers={**ORIGIN, 'X-CSRF-Token': csrf})).status_code == 204
    assert (await client.get('/api/auth/me')).status_code == 401


@pytest.mark.asyncio
async def test_browser_login_rejects_cross_origin_and_requires_origin(client):
    payload = {'email': 'browser@example.com', 'password': 'password123'}
    assert (await client.post('/api/auth/browser/register', json=payload)).status_code == 403
    assert (await client.post('/api/auth/browser/register', headers={'Origin': 'https://attacker.invalid'}, json=payload)).status_code == 403
    assert (await register(client)).status_code == 201
    csrf = (await client.get('/api/auth/browser/session')).json()['csrf_token']
    assert (await client.post('/api/auth/browser/logout', headers={'Origin': 'https://attacker.invalid', 'X-CSRF-Token': csrf})).status_code == 403


@pytest.mark.asyncio
async def test_logout_revokes_cookie_replay_and_session_is_hashed(client, db_session):
    from app.database.models.browser_session import BrowserSession
    response = await register(client)
    raw = client.cookies.get('algoflow_session')
    row = await db_session.scalar(select(BrowserSession))
    assert row.token_hash != raw and len(row.token_hash) == 64
    csrf = response.json()['csrf_token']
    assert (await client.post('/api/auth/browser/logout', headers={**ORIGIN, 'X-CSRF-Token': csrf})).status_code == 204
    client.cookies.set('algoflow_session', raw)
    assert (await client.get('/api/auth/me')).status_code == 401


@pytest.mark.asyncio
async def test_password_version_and_expiry_invalidate_browser_session(client, db_session):
    from app.database.models.browser_session import BrowserSession
    from app.database.models.user import User
    from datetime import datetime, timedelta, timezone
    response = await register(client)
    user = await db_session.get(User, response.json()['user']['id'])
    user.auth_version += 1
    await db_session.commit()
    assert (await client.get('/api/auth/me')).status_code == 401
    client.cookies.clear()
    response = await client.post('/api/auth/browser/login', headers=ORIGIN, json={'email': user.email, 'password': 'password123'})
    assert response.status_code == 200
    row = await db_session.scalar(select(BrowserSession).where(BrowserSession.auth_version == 1))
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()
    assert (await client.get('/api/auth/me')).status_code == 401


@pytest.mark.asyncio
async def test_invalid_cookie_cleared_before_public_password_recovery(client):
    client.cookies.set('algoflow_session', 'invalid-session')
    response = await client.get('/api/auth/browser/session')
    assert response.status_code == 401
    assert 'max-age=0' in response.headers['set-cookie'].lower()
    assert (await client.post('/api/auth/browser/register',headers=ORIGIN,
        json={'email':'clear-cookie@example.com','password':'password123'})).status_code == 201


@pytest.mark.asyncio
async def test_production_cookies_secure_and_legacy_bearers_refused(client, monkeypatch):
    from app.core.config import get_settings
    response=await client.post('/api/auth/register',json={'email':'secure-cookie@example.com','password':'password123'})
    token=response.json()['access_token']
    monkeypatch.setattr(get_settings(),'environment','production')
    assert (await client.get('/api/auth/me',headers={'Authorization':'Bearer '+token})).status_code == 401
    assert (await client.post('/api/auth/login',json={'email':'secure-cookie@example.com','password':'password123'})).status_code == 410
    response=await client.post('/api/auth/browser/login',headers=ORIGIN,
        json={'email':'secure-cookie@example.com','password':'password123'})
    assert response.status_code==200
    cookie=response.headers['set-cookie'].lower()
    assert '__host-algoflow_session=' in cookie and '; secure' in cookie and '; httponly' in cookie


@pytest.mark.asyncio
async def test_non_ascii_csrf_proof_is_rejected_without_server_error(client):
    await register(client)
    response=await client.post('/api/auth/browser/logout',headers=[(b'Origin',ORIGIN['Origin'].encode()),(b'X-CSRF-Token',b'\xff')])
    assert response.status_code==403


@pytest.mark.asyncio
async def test_cookie_auth_preserves_strategy_ownership(client):
    from tests.test_strategies_api import _valid_graph
    first=await register(client)
    headers={**ORIGIN,'X-CSRF-Token':first.json()['csrf_token']}
    saved=await client.post('/api/strategies',headers=headers,json={'name':'Private cookie algorithm','graph':_valid_graph()})
    assert saved.status_code==201, saved.text
    strategy_id=saved.json()['id']
    await client.post('/api/auth/browser/logout',headers=headers)
    second=await register(client,'other-browser@example.com')
    headers={**ORIGIN,'X-CSRF-Token':second.json()['csrf_token']}
    assert (await client.get('/api/strategies')).json()==[]
    assert (await client.get('/api/strategies/'+strategy_id)).status_code==404
    assert (await client.put('/api/strategies/'+strategy_id,headers=headers,json={'name':'Stolen','graph':_valid_graph()})).status_code==404
    assert (await client.delete('/api/strategies/'+strategy_id,headers=headers)).status_code==404
