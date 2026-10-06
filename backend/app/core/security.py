"""Password hashing, JWT issuance/verification, and at-rest secret encryption.

Nothing here ever logs a secret. Callers are responsible for keeping raw
passwords, tokens, and API keys out of log statements.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

settings = get_settings()

_TOKEN_TYPE_ACCESS = "access"


# --- Passwords ---------------------------------------------------------

def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False


# --- JWT -----------------------------------------------------------------

def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": _TOKEN_TYPE_ACCESS,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


class TokenError(Exception):
    """Raised when a JWT is missing, malformed, expired, or the wrong type."""


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm], options={"require": ["sub", "exp", "iat", "type"]})
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Invalid token") from exc

    if payload.get("type") != _TOKEN_TYPE_ACCESS:
        raise TokenError("Invalid token type")
    return payload


# --- Secret encryption (exchange API keys/secrets at rest) --------------

def _fernet() -> Fernet:
    return Fernet(settings.encryption_key.encode("utf-8"))


def encrypt_secret(plain_text: str) -> str:
    return _fernet().encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_secret(cipher_text: str) -> str:
    try:
        return _fernet().decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt secret — wrong key or corrupted value") from exc
