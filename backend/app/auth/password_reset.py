"""User-row locking serializes password recovery; completion consumes all links."""
import asyncio
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, update
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.core.security import hash_password
from app.database.database import AsyncSessionLocal
from app.database.models.user import User
from app.database.models.password_reset import PasswordResetToken
from app.auth.mail import send_reset_email, send_reset_confirmation

logger = get_logger(__name__)


def digest(token): return hashlib.sha256(token.encode()).hexdigest()


async def deliver_reset_link(email):
    """Run after the uniform response. Delivery failures remain redacted."""
    token_hash = None
    try:
        settings = get_settings()
        async with AsyncSessionLocal() as db:
            user = (await db.execute(select(User).where(User.email == email, User.is_active.is_(True))
                .with_for_update())).scalar_one_or_none()
            if user is None: return
            raw = secrets.token_urlsafe(32)
            token_hash = digest(raw)
            now = datetime.now(timezone.utc)
            row = PasswordResetToken(token_hash=token_hash, user_id=user.id,
                auth_version=user.auth_version, created_at=now,
                expires_at=now + timedelta(minutes=settings.password_reset_expire_minutes))
            db.add(row)
            recipient = user.email
            await db.commit()
        link = settings.password_reset_frontend_url.rstrip('/') + '/reset-password#token=' + raw
        await send_reset_email(recipient, link, settings.password_reset_expire_minutes)
    except Exception:
        # A failed delivery cannot leave its token usable. Never echo SMTP errors.
        if token_hash:
            try:
                async with AsyncSessionLocal() as db:
                    await db.execute(update(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
                        .values(used_at=datetime.now(timezone.utc)))
                    await db.commit()
            except Exception: pass
        logger.warning('Password reset delivery failed; check SMTP configuration and connectivity.')


async def complete_reset(db, token, password):
    key = digest(token)
    owner = await db.scalar(select(PasswordResetToken.user_id).where(PasswordResetToken.token_hash == key))
    invalid = AppError('RESET_LINK_INVALID', 'This reset link is invalid or expired. Request a new link.', 400)
    if owner is None: raise invalid
    # Always acquire the user lock before any token lock, including issuance.
    user = (await db.execute(select(User).where(User.id == owner).with_for_update()
        .execution_options(populate_existing=True))).scalar_one_or_none()
    row = (await db.execute(select(PasswordResetToken).where(PasswordResetToken.token_hash == key)
        .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if user is None or not user.is_active or row is None or row.used_at is not None or row.auth_version != user.auth_version or row.expires_at.replace(tzinfo=timezone.utc) <= now:
        raise invalid
    user.hashed_password = await asyncio.to_thread(hash_password, password)
    user.auth_version += 1
    await db.execute(update(PasswordResetToken).where(PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None)).values(used_at=now))
    await db.commit()
    from app.redis.pubsub import publish_user_event
    await publish_user_event(user.id, 'session_revoked', {'reason':'password_reset'})
    return user.email


async def deliver_confirmation(email):
    try: await send_reset_confirmation(email)
    except Exception: logger.warning('Password reset confirmation delivery failed; check SMTP configuration and connectivity.')
