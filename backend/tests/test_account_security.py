import pytest
from datetime import datetime, timezone
from sqlalchemy import select
from tests.test_browser_sessions import ORIGIN, register

pytestmark = pytest.mark.asyncio


async def csrf_headers(client):
    response = await client.get('/api/auth/browser/session')
    return {**ORIGIN, 'X-CSRF-Token': response.json()['csrf_token']}


async def test_mfa_enrollment_requires_password_and_code_then_protects_login(client):
    import pyotp
    await register(client)
    headers = await csrf_headers(client)
    bad = await client.post('/api/security/mfa/enroll', headers=headers, json={'password': 'wrong'})
    assert bad.status_code == 401
    enrolled = await client.post('/api/security/mfa/enroll', headers=headers, json={'password': 'password123'})
    assert enrolled.status_code == 200, enrolled.text
    secret = enrolled.json()['secret']
    assert (await client.get('/api/security/status')).json()['mfa_enabled'] is False
    assert (await client.post('/api/security/mfa/confirm', headers=headers, json={'code': 'bad'})).status_code == 422
    code = pyotp.TOTP(secret).now()
    confirmed = await client.post('/api/security/mfa/confirm', headers=headers, json={'code': code})
    assert confirmed.status_code == 200, confirmed.text
    assert (await client.get('/api/security/status')).json()['mfa_enabled'] is True
    headers = await csrf_headers(client)
    assert (await client.post('/api/security/mfa/enroll', headers=headers, json={'password':'password123'})).status_code == 409
    await client.post('/api/auth/browser/logout', headers=headers)
    login = {'email':'browser@example.com', 'password':'password123'}
    assert (await client.post('/api/auth/browser/login', headers=ORIGIN, json=login)).status_code == 401
    assert (await client.post('/api/auth/browser/login', headers=ORIGIN, json={**login, 'totp_code':code})).status_code == 401  # replay
    future = pyotp.TOTP(secret).at(datetime.now(timezone.utc).timestamp() + 30)
    assert (await client.post('/api/auth/browser/login', headers=ORIGIN, json={**login, 'totp_code':future})).status_code == 200


async def test_step_up_requires_mfa_and_rejects_code_reuse(client):
    import pyotp
    from app.auth.account_security import require_live_user
    from app.core.exceptions import AppError
    await register(client)
    headers = await csrf_headers(client)
    response = await client.post('/api/security/step-up', headers=headers, json={'password':'password123','code':'123456'})
    assert response.status_code == 403
    secret = (await client.post('/api/security/mfa/enroll', headers=headers, json={'password':'password123'})).json()['secret']
    await client.post('/api/security/mfa/confirm', headers=headers, json={'code':pyotp.TOTP(secret).now()})
    headers = await csrf_headers(client)
    future = pyotp.TOTP(secret).at(datetime.now(timezone.utc).timestamp() + 30)
    payload = {'password':'password123','code':future}
    assert (await client.post('/api/security/step-up', headers=headers, json=payload)).status_code == 200
    assert (await client.post('/api/security/step-up', headers=headers, json=payload)).status_code == 401


async def test_verification_is_user_scoped_expiring_single_use(client, db_session):
    from app.database.models.account_security import EmailVerificationToken, AccountSecurity
    from app.auth.sessions import digest
    from datetime import timedelta
    response = await register(client)
    owner = response.json()['user']['id']
    now = datetime.now(timezone.utc)
    token = 'v' * 43
    db_session.add(EmailVerificationToken(token_hash=digest(token), user_id=owner, auth_version=0,
        created_at=now, expires_at=now+timedelta(hours=1)))
    await db_session.commit()
    assert (await client.get('/api/security/status')).json()['email_verified'] is False
    headers = await csrf_headers(client)
    result = await client.post('/api/security/email/verify', headers=headers, json={'token':token})
    assert result.status_code == 200, result.text
    assert (await client.get('/api/security/status')).json()['email_verified'] is True
    assert (await client.post('/api/security/email/verify', headers=headers, json={'token':token})).status_code == 400
    # A second user must not be able to consume an UNUSED first-user token.
    other_token = 'u' * 43
    db_session.add(EmailVerificationToken(token_hash=digest(other_token), user_id=owner, auth_version=0,
        created_at=now, expires_at=now+timedelta(hours=1)))
    await db_session.commit()
    await client.post('/api/auth/browser/logout', headers=headers)
    await register(client, 'other@example.com')
    result = await client.post('/api/security/email/verify', headers=await csrf_headers(client), json={'token':other_token})
    assert result.status_code == 400
    unused = await db_session.get(EmailVerificationToken, digest(other_token), populate_existing=True)
    assert unused.used_at is None
    row = await db_session.get(AccountSecurity, owner)
    assert row.email_verified_at is not None


async def test_password_reset_keeps_mfa_enabled(client, db_session):
    from app.auth.password_reset import complete_reset
    from app.auth.sessions import digest
    from app.database.models.password_reset import PasswordResetToken
    from app.database.models.account_security import AccountSecurity
    from app.core.security import encrypt_secret
    from datetime import timedelta
    response = await register(client)
    owner = response.json()['user']['id']
    now = datetime.now(timezone.utc)
    db_session.add(AccountSecurity(user_id=owner, mfa_secret_encrypted=encrypt_secret('JBSWY3DPEHPK3PXP')))
    db_session.add(PasswordResetToken(token_hash=digest('r'*43), user_id=owner, auth_version=0,
        created_at=now, expires_at=now+timedelta(minutes=10)))
    await db_session.commit()
    await complete_reset(db_session, 'r'*43, 'changed-password123')
    assert (await client.get('/api/auth/me')).status_code == 401
    assert (await db_session.get(AccountSecurity, owner)).mfa_secret_encrypted is not None
    assert (await client.post('/api/auth/browser/login', headers=ORIGIN,
        json={'email':'browser@example.com','password':'changed-password123'})).status_code == 401


async def test_expired_enrollment_and_email_token_fail_closed(client, db_session):
    import pyotp
    from datetime import timedelta
    from app.database.models.account_security import AccountSecurity, EmailVerificationToken
    from app.auth.sessions import digest
    response=await register(client)
    uid=response.json()['user']['id']
    headers=await csrf_headers(client)
    secret=(await client.post('/api/security/mfa/enroll',headers=headers,json={'password':'password123'})).json()['secret']
    row=await db_session.get(AccountSecurity,uid)
    row.pending_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
    token='x'*43
    db_session.add(EmailVerificationToken(token_hash=digest(token),user_id=uid,auth_version=0,
        created_at=datetime.now(timezone.utc)-timedelta(hours=2),expires_at=datetime.now(timezone.utc)-timedelta(hours=1)))
    await db_session.commit()
    assert (await client.post('/api/security/mfa/confirm',headers=headers,json={'code':pyotp.TOTP(secret).now()})).status_code==409
    assert (await client.post('/api/security/email/verify',headers=headers,json={'token':token})).status_code==400


async def test_live_credentials_require_fresh_mfa_after_verified_enrollment(client, db_session):
    from app.database.models.account_security import AccountSecurity
    from app.database.models.browser_session import BrowserSession
    from app.auth.sessions import digest
    from app.core.security import encrypt_secret
    from datetime import timedelta
    response=await register(client)
    uid=response.json()['user']['id']
    db_session.add(AccountSecurity(user_id=uid,email_verified_at=datetime.now(timezone.utc),
        mfa_secret_encrypted=encrypt_secret('JBSWY3DPEHPK3PXP')))
    session=await db_session.get(BrowserSession,digest(client.cookies.get('algoflow_session')))
    session.mfa_at=datetime.now(timezone.utc)-timedelta(minutes=6)
    await db_session.commit()
    result=await client.post('/api/exchanges/connect',headers=await csrf_headers(client),
        json={'exchange_name':'binanceusdm','api_key':'fake','api_secret':'fake','is_testnet':False})
    assert result.status_code==403 and result.json()['error']['code']=='STEP_UP_REQUIRED'
