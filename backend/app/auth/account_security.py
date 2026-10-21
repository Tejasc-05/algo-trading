"""Verified email and replay-resistant TOTP under a consistent user-row lock."""
import asyncio
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import pyotp
from sqlalchemy import select, update

from app.auth.sessions import cookie_name, digest, resolve_session, utc
from app.core.exceptions import AppError, UnauthorizedError, RateLimitedError
from app.core.security import decrypt_secret, encrypt_secret, verify_password
from app.database.models.account_security import AccountSecurity, EmailVerificationToken
from app.database.models.user import User


async def limit_user(redis, user_id, action, maximum=5):
    from app.redis.cache import increment_with_expiry
    count = await increment_with_expiry(redis, f'ratelimit:security:{action}:{user_id}', 900)
    if count > maximum:
        raise RateLimitedError('Too many security attempts. Try again later.')


async def locked_user(db, user_id):
    user = await db.scalar(select(User).where(User.id == user_id).with_for_update()
        .execution_options(populate_existing=True))
    if user is None or not user.is_active:
        raise UnauthorizedError('Account is unavailable')
    return user


async def security_row(db, user_id, create=False):
    # Callers that mutate must acquire locked_user first, including first enrollment.
    row = await db.get(AccountSecurity, user_id, populate_existing=True)
    if row is None and create:
        row = AccountSecurity(user_id=user_id, last_mfa_counter=-1)
        db.add(row)
        await db.flush()
    return row


async def check_password(user, password):
    if not await asyncio.to_thread(verify_password, password, user.hashed_password):
        raise UnauthorizedError('Password confirmation failed')


def consume_code(row, code, pending=False):
    encrypted = row.pending_secret_encrypted if pending else row.mfa_secret_encrypted
    if not encrypted or not code or len(code) != 6 or not code.isascii() or not code.isdigit():
        raise UnauthorizedError('Enter a new code from your authenticator app', code='MFA_REQUIRED')
    totp = pyotp.TOTP(decrypt_secret(encrypted))
    counter = totp.timecode(datetime.now(timezone.utc))
    for candidate in (counter, counter-1, counter+1):
        if candidate > row.last_mfa_counter and hmac.compare_digest(totp.at(candidate*30), code):
            row.last_mfa_counter = candidate
            return
    raise UnauthorizedError('Code is invalid, expired or already used. Wait for a new code.', code='MFA_REQUIRED')


async def check_login_mfa(db, user, code):
    row = await security_row(db, user.id)
    if row and row.mfa_secret_encrypted:
        consume_code(row, code)
        return True
    return False


async def enroll(db, user_id, password):
    user = await locked_user(db, user_id)
    await check_password(user, password)
    row = await security_row(db, user.id, create=True)
    if row.mfa_secret_encrypted:
        raise AppError('MFA_ALREADY_ENABLED', 'MFA is already enabled. Replacing it requires account recovery.', 409)
    secret = pyotp.random_base32()
    row.pending_secret_encrypted = encrypt_secret(secret)
    row.pending_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    row.last_mfa_counter = -1
    await db.commit()
    return {'secret': secret, 'provisioning_uri': pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name='AlgoFlow'),
        'expires_in_seconds': 600}


async def confirm_enrollment(db, user_id, code, session_token):
    user = await locked_user(db, user_id)
    await resolve_session(db, session_token)
    row = await security_row(db, user.id)
    now = datetime.now(timezone.utc)
    if row is None or row.mfa_secret_encrypted or row.pending_expires_at is None or utc(row.pending_expires_at) <= now:
        raise AppError('MFA_ENROLLMENT_EXPIRED', 'Start authenticator setup again.', 409)
    consume_code(row, code, pending=True)
    row.mfa_secret_encrypted = row.pending_secret_encrypted
    row.pending_secret_encrypted = None
    row.pending_expires_at = None
    user.auth_version += 1
    # The route rotates the current browser session and commits this transaction.
    return user


async def step_up(db, request, user_id, password, code):
    user = await locked_user(db, user_id)
    _, session = await resolve_session(db, request.cookies.get(cookie_name()))
    await check_password(user, password)
    row = await security_row(db, user.id)
    if row is None or not row.mfa_secret_encrypted:
        raise AppError('MFA_SETUP_REQUIRED', 'Set up an authenticator app first.', 403)
    consume_code(row, code)
    session.mfa_at = datetime.now(timezone.utc)
    await db.commit()


async def require_live_user(db, request, user):
    # Serialize sensitive changes with password reset/MFA enrollment. Re-read
    # the session after acquiring the lock, not just at route authentication.
    await locked_user(db, user.id)
    _, session = await resolve_session(db, request.cookies.get(cookie_name()))
    row = await security_row(db, user.id)
    if row is None or row.email_verified_at is None:
        raise AppError('EMAIL_VERIFICATION_REQUIRED', 'Verify your email address before adding live credentials.', 403)
    if not row.mfa_secret_encrypted:
        raise AppError('MFA_SETUP_REQUIRED', 'Enable an authenticator app before adding live credentials.', 403)
    now = datetime.now(timezone.utc)
    if session.mfa_at is None or not timedelta(0) <= now - utc(session.mfa_at) <= timedelta(minutes=5):
        raise AppError('STEP_UP_REQUIRED', 'Confirm your password and a new authenticator code.', 403)


async def verify_email(db, user_id, token):
    user = await locked_user(db, user_id)
    row = await db.get(EmailVerificationToken, digest(token), populate_existing=True)
    now = datetime.now(timezone.utc)
    if (row is None or row.user_id != user.id or row.auth_version != user.auth_version
            or row.used_at is not None or utc(row.expires_at) <= now):
        raise AppError('VERIFICATION_LINK_INVALID', 'This verification link is invalid or expired.', 400)
    security = await security_row(db, user.id, create=True)
    security.email_verified_at = now
    await db.execute(update(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id,
        EmailVerificationToken.used_at.is_(None)).values(used_at=now))
    await db.commit()


async def deliver_verification(user_id):
    """Mail delivery is redacted. Durable delivery is a separate release blocker."""
    from app.auth.mail import require_mail_configuration, _send
    from app.database.database import AsyncSessionLocal
    from app.core.logging import get_logger
    token_hash = None
    try:
        settings = require_mail_configuration()
        async with AsyncSessionLocal() as db:
            user = await locked_user(db, user_id)
            row = await security_row(db, user.id)
            if row and row.email_verified_at:
                return
            raw = secrets.token_urlsafe(32)
            token_hash = digest(raw)
            now = datetime.now(timezone.utc)
            db.add(EmailVerificationToken(token_hash=token_hash, user_id=user.id, auth_version=user.auth_version,
                created_at=now, expires_at=now + timedelta(hours=1)))
            recipient = user.email
            await db.commit()
        link = settings.password_reset_frontend_url.rstrip('/') + '/verify-email#token=' + raw
        await asyncio.to_thread(_send, recipient, 'Verify your AlgoFlow email',
            f'Open this link while signed into the same AlgoFlow account:\n\n{link}\n\nThis single-use link expires in one hour.')
    except Exception:
        if token_hash:
            try:
                async with AsyncSessionLocal() as db:
                    await db.execute(update(EmailVerificationToken).where(EmailVerificationToken.token_hash == token_hash)
                        .values(used_at=datetime.now(timezone.utc)))
                    await db.commit()
            except Exception:
                pass
        get_logger(__name__).warning('Email verification delivery failed; check mail configuration.')
