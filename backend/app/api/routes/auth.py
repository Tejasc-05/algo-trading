import asyncio
from fastapi import APIRouter, Depends, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import RateLimiter, get_db, get_current_user, get_redis
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.exceptions import AppError
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.database.models.user import User
from app.database.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut, ForgotPasswordRequest, ResetPasswordRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RateLimiter("register"))],
)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    if get_settings().environment == 'production':
        raise AppError('BROWSER_AUTH_REQUIRED', 'Use browser session authentication.', 410)
    repo = UserRepository(db)
    if await repo.get_by_email(payload.email) is not None:
        raise ConflictError("An account with this email already exists", code="EMAIL_TAKEN")

    user = User(
        email=payload.email.lower(),
        hashed_password=await asyncio.to_thread(hash_password, payload.password),
        full_name=payload.full_name,
    )
    repo.add(user)
    try:
        await repo.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("An account with this email already exists", code="EMAIL_TAKEN") from None

    token = create_access_token(subject=user.id, extra_claims={"ver":user.auth_version})
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(RateLimiter("login"))])
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db), redis=Depends(get_redis)) -> TokenResponse:
    if get_settings().environment == 'production':
        raise AppError('BROWSER_AUTH_REQUIRED', 'Use browser session authentication.', 410)
    from app.auth.account_security import limit_user
    from app.auth.sessions import digest
    await limit_user(redis, digest(str(payload.email).lower()), 'login', 10)
    repo = UserRepository(db)
    user = await repo.get_by_email(payload.email)
    if user is None or not await asyncio.to_thread(verify_password, payload.password, user.hashed_password):
        raise UnauthorizedError("Invalid email or password", code="INVALID_CREDENTIALS")
    if not user.is_active:
        raise UnauthorizedError("This account is inactive", code="ACCOUNT_INACTIVE")

    from app.auth.account_security import locked_user, check_login_mfa
    user = await locked_user(db, user.id)
    # Recheck under the same lock used by password reset and MFA mutation.
    if not await asyncio.to_thread(verify_password, payload.password, user.hashed_password):
        raise UnauthorizedError('Invalid email or password', code='INVALID_CREDENTIALS')
    await check_login_mfa(db, user, payload.totp_code)
    await db.commit()

    token = create_access_token(subject=user.id, extra_claims={"ver":user.auth_version})
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))

# Added endpoint to get current logged-in user
@router.get(
    "/me",
    response_model=UserOut,
    dependencies=[Depends(RateLimiter("me"))],
)
async def read_current_user(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)


@router.post('/forgot-password', status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(RateLimiter('password-reset-request', max_attempts=5, window_seconds=900))])
async def forgot_password(payload: ForgotPasswordRequest, background: BackgroundTasks, redis=Depends(get_redis)):
    from app.auth.mail import require_mail_configuration
    from app.auth.password_reset import deliver_reset_link, digest
    from app.redis.cache import increment_with_expiry
    from app.core.exceptions import RateLimitedError
    require_mail_configuration()
    email = str(payload.email).lower()
    count = await increment_with_expiry(redis, f'ratelimit:reset-email:{digest(email)}', 3600)
    if count > 3: raise RateLimitedError('Too many reset requests for this address. Please try again later.')
    background.add_task(deliver_reset_link, email)
    return {'message':'If an active account exists for this email, you will receive a password reset link.'}


@router.post('/reset-password', dependencies=[Depends(RateLimiter('password-reset-complete', max_attempts=10, window_seconds=900))])
async def reset_password(payload: ResetPasswordRequest, background: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    from app.auth.password_reset import complete_reset, deliver_confirmation
    email = await complete_reset(db, payload.token, payload.password)
    background.add_task(deliver_confirmation, email)
    return {'message':'Password reset successfully. Sign in with your new password.'}
