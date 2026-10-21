"""Account recovery changes passwords only with a current, unused secret link."""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, parse_qs
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import select
from app.core.config import get_settings
from app.database.models.password_reset import PasswordResetToken
from app.database.models.user import User
from app.auth import password_reset
from tests.conftest import TestSessionLocal


@pytest.fixture
def recovery(monkeypatch):
    settings=get_settings()
    for key,value in {'smtp_host':'mail.example.com','smtp_port':587,'smtp_from_email':'noreply@example.com',
        'smtp_starttls':True,'smtp_ssl':False,'password_reset_frontend_url':'http://localhost:5173',
        'environment':'development','password_reset_expire_minutes':30}.items():
        monkeypatch.setattr(settings,key,value)
    monkeypatch.setattr(password_reset,'AsyncSessionLocal',TestSessionLocal)
    sent=[]
    async def send(email,link,minutes): sent.append((email,link,minutes))
    monkeypatch.setattr(password_reset,'send_reset_email',send)
    monkeypatch.setattr(password_reset,'send_reset_confirmation',AsyncMock())
    return sent


def token(sent,index=-1): return parse_qs(urlparse(sent[index][1]).fragment)['token'][0]


@pytest.mark.asyncio
async def test_reset_flow_is_single_use_and_preserves_owned_data(client,auth_headers,db_session,recovery):
    from tests.test_api_endpoints import _create_test_strategy
    strategy=await _create_test_strategy(client,auth_headers)
    old_user=(await client.get('/api/auth/me',headers=auth_headers)).json()
    r=await client.post('/api/auth/forgot-password',json={'email':'STRATEGY-OWNER@EXAMPLE.COM'})
    assert r.status_code==202 and 'token' not in r.json() and 'link' not in r.json()
    assert len(recovery)==1 and recovery[0][0]=='strategy-owner@example.com'
    assert recovery[0][2]==30 and urlparse(recovery[0][1]).query==''
    raw=token(recovery)
    row=await db_session.get(PasswordResetToken,password_reset.digest(raw))
    assert row is not None and row.token_hash != raw
    assert (await client.get('/api/auth/me',headers=auth_headers)).status_code==200
    body={'token':raw,'password':'new-password123','confirm_password':'new-password123'}
    result=await client.post('/api/auth/reset-password',json=body)
    assert result.status_code==200
    assert (await client.post('/api/auth/reset-password',json=body)).status_code==400
    assert (await client.get('/api/auth/me',headers=auth_headers)).status_code==401
    assert (await client.post('/api/auth/login',json={'email':old_user['email'],'password':'password123'})).status_code==401
    login=await client.post('/api/auth/login',json={'email':old_user['email'],'password':'new-password123'})
    assert login.status_code==200
    headers={'Authorization':'Bearer '+login.json()['access_token']}
    assert (await client.get('/api/auth/me',headers=headers)).json()['id']==old_user['id']
    assert [s['id'] for s in (await client.get('/api/strategies',headers=headers)).json()]==[strategy]
    password_reset.send_reset_confirmation.assert_awaited_once_with(old_user['email'])


@pytest.mark.asyncio
async def test_unknown_and_inactive_accounts_get_same_response_without_email(client,auth_headers,db_session,recovery):
    known=await client.post('/api/auth/forgot-password',json={'email':'strategy-owner@example.com'})
    unknown=await client.post('/api/auth/forgot-password',json={'email':'unknown@example.com'})
    assert known.status_code==unknown.status_code==202 and known.json()==unknown.json()
    user=await db_session.scalar(select(User).where(User.email=='strategy-owner@example.com'))
    user.is_active=False; await db_session.commit()
    inactive=await client.post('/api/auth/forgot-password',json={'email':user.email})
    assert inactive.json()==known.json() and len(recovery)==1


@pytest.mark.asyncio
async def test_expired_unknown_and_mismatched_links_do_not_change_password(client,auth_headers,db_session,recovery):
    await client.post('/api/auth/forgot-password',json={'email':'strategy-owner@example.com'})
    row=await db_session.get(PasswordResetToken,password_reset.digest(token(recovery)))
    row.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1); await db_session.commit()
    for raw in [token(recovery),'x'*43]:
        r=await client.post('/api/auth/reset-password',json={'token':raw,'password':'new-password123','confirm_password':'new-password123'})
        assert r.status_code==400 and r.json()['error']['code']=='RESET_LINK_INVALID'
    assert (await client.get('/api/auth/me',headers=auth_headers)).status_code==200
    r=await client.post('/api/auth/reset-password',json={'token':token(recovery),'password':'new-password123','confirm_password':'different-password'})
    assert r.status_code==422
    r=await client.post('/api/auth/reset-password',json={'token':token(recovery),'password':'😀'*20,'confirm_password':'😀'*20})
    assert r.status_code==422


@pytest.mark.asyncio
async def test_completion_invalidates_every_outstanding_link(client,auth_headers,recovery):
    for _ in range(2): await client.post('/api/auth/forgot-password',json={'email':'strategy-owner@example.com'})
    for index,status in [(0,200),(1,400)]:
        r=await client.post('/api/auth/reset-password',json={'token':token(recovery,index),'password':'new-password123','confirm_password':'new-password123'})
        assert r.status_code==status


@pytest.mark.asyncio
async def test_mail_not_configured_is_uniform_and_creates_no_tokens(client,auth_headers,db_session,monkeypatch):
    monkeypatch.setattr(get_settings(),'smtp_host',None)
    for email in ['strategy-owner@example.com','unknown@example.com']:
        r=await client.post('/api/auth/forgot-password',json={'email':email})
        assert r.status_code==503 and r.json()['error']['code']=='EMAIL_NOT_CONFIGURED'
    assert list((await db_session.scalars(select(PasswordResetToken))).all())==[]


@pytest.mark.asyncio
async def test_delivery_failure_is_redacted_and_token_cannot_be_used(client,auth_headers,db_session,recovery,monkeypatch,caplog):
    async def fail(*args): raise RuntimeError('sensitive-smtp-password-and-reset-token')
    monkeypatch.setattr(password_reset,'send_reset_email',fail)
    assert (await client.post('/api/auth/forgot-password',json={'email':'strategy-owner@example.com'})).status_code==202
    rows=list((await db_session.scalars(select(PasswordResetToken))).all())
    assert len(rows)==1 and rows[0].used_at is not None
    assert 'sensitive-smtp-password-and-reset-token' not in caplog.text
    assert (await client.get('/api/auth/me',headers=auth_headers)).status_code==200


@pytest.mark.asyncio
async def test_reset_request_rate_limit_uses_normalized_email(client,auth_headers,recovery):
    for _ in range(3):
        assert (await client.post('/api/auth/forgot-password',json={'email':'strategy-owner@example.com'})).status_code==202
    r=await client.post('/api/auth/forgot-password',json={'email':'STRATEGY-OWNER@EXAMPLE.COM'})
    assert r.status_code==429 and len(recovery)==3


@pytest.mark.parametrize('url',['https://attacker.example/?redirect=anything','http://production.example','https://user:password@example.com','https://example.com/path'])
def test_bad_reset_origins_are_rejected(recovery,monkeypatch,url):
    from app.auth.mail import require_mail_configuration
    from app.core.exceptions import AppError
    monkeypatch.setattr(get_settings(),'password_reset_frontend_url',url)
    with pytest.raises(AppError): require_mail_configuration()


@pytest.mark.asyncio
async def test_existing_websocket_cannot_receive_after_reset(monkeypatch):
    from app.websocket.manager import _relay_redis_to_websocket
    from types import SimpleNamespace
    ws=SimpleNamespace(send_text=AsyncMock(),close=AsyncMock())
    monkeypatch.setattr('app.api.dependencies.get_user_from_websocket',AsyncMock(return_value=None))
    async def messages(): yield '{"event":"portfolio_update","data":{"balance":100}}'
    await _relay_redis_to_websocket('owner',ws,messages())
    ws.send_text.assert_not_awaited()
    assert ws.close.await_args_list[0].kwargs['code']==1008
