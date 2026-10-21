"""Database-backed browser authentication and session-bound CSRF tokens."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError
from app.database.models.browser_session import BrowserSession
from app.database.models.user import User


def cookie_name():
    return '__Host-algoflow_session' if get_settings().environment == 'production' else 'algoflow_session'


def digest(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def csrf_token(raw):
    return hmac.new(get_settings().jwt_secret.encode(), ('csrf:' + raw).encode(), hashlib.sha256).hexdigest()


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def resolve_session(db, raw):
    if not raw or len(raw) > 128:
        raise UnauthorizedError('Session expired. Sign in again.')
    row = await db.get(BrowserSession, digest(raw), populate_existing=True)
    user = await db.get(User, row.user_id, populate_existing=True) if row else None
    if (row is None or row.revoked_at is not None or utc(row.expires_at) <= datetime.now(timezone.utc)
            or user is None or not user.is_active or user.auth_version != row.auth_version):
        raise UnauthorizedError('Session expired. Sign in again.')
    return user, row


async def issue_session(db, response, user, previous=None, mfa=False):
    now = datetime.now(timezone.utc)
    if previous:
        old = await db.get(BrowserSession, digest(previous))
        if old:
            old.revoked_at = now
    raw = secrets.token_urlsafe(32)
    ttl = get_settings().access_token_expire_minutes * 60
    row = BrowserSession(token_hash=digest(raw), user_id=user.id, auth_version=user.auth_version,
        created_at=now, expires_at=now + timedelta(seconds=ttl), mfa_at=now if mfa else None)
    db.add(row)
    await db.commit()
    response.set_cookie(cookie_name(), raw, max_age=ttl, httponly=True,
        secure=get_settings().environment == 'production', samesite='strict', path='/')
    return csrf_token(raw)
