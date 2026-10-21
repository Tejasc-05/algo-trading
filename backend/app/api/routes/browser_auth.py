"""Browser-only auth contract; no bearer token is returned to JavaScript."""
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import RateLimiter, get_db, get_redis
from app.auth.sessions import cookie_name, csrf_token, issue_session, resolve_session
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import hash_password, verify_password
from app.database.models.user import User
from app.schemas.auth import RegisterRequest, LoginRequest, UserOut

router = APIRouter(prefix='/auth/browser', tags=['browser-auth'])


def view(user, csrf):
    return {'user': UserOut.model_validate(user), 'csrf_token': csrf}


@router.post('/register', status_code=201, dependencies=[Depends(RateLimiter('register'))])
async def register(payload: RegisterRequest, request: Request, response: Response, db=Depends(get_db)):
    email = str(payload.email).lower()
    if await db.scalar(select(User.id).where(User.email == email)):
        raise ConflictError('An account with this email already exists', code='EMAIL_TAKEN')
    user = User(email=email, hashed_password=await asyncio.to_thread(hash_password, payload.password), full_name=payload.full_name)
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError('An account with this email already exists', code='EMAIL_TAKEN') from None
    token = await issue_session(db, response, user, request.cookies.get(cookie_name()))
    await db.refresh(user)
    return view(user, token)


@router.post('/login', dependencies=[Depends(RateLimiter('login'))])
async def login(payload: LoginRequest, request: Request, response: Response, db=Depends(get_db), redis=Depends(get_redis)):
    from app.auth.account_security import limit_user
    from app.auth.sessions import digest
    await limit_user(redis, digest(str(payload.email).lower()), 'login', 10)
    user = await db.scalar(select(User).where(User.email == str(payload.email).lower()).with_for_update()
        .execution_options(populate_existing=True))
    if user is None or not await asyncio.to_thread(verify_password, payload.password, user.hashed_password) or not user.is_active:
        raise UnauthorizedError('Invalid email or password', code='INVALID_CREDENTIALS')
    from app.auth.account_security import check_login_mfa
    mfa = await check_login_mfa(db, user, payload.totp_code)
    return view(user, await issue_session(db, response, user, request.cookies.get(cookie_name()), mfa=mfa))


@router.get('/session')
async def session(request: Request, db=Depends(get_db)):
    raw = request.cookies.get(cookie_name())
    try:
        user, _ = await resolve_session(db, raw)
    except UnauthorizedError:
        from fastapi.responses import JSONResponse
        response = JSONResponse({'error': {'code': 'UNAUTHORIZED', 'message': 'Sign in again.'}}, status_code=401)
        response.delete_cookie(cookie_name(), path='/', httponly=True,
            secure=cookie_name().startswith('__Host-'), samesite='strict')
        return response
    return view(user, csrf_token(raw))


@router.post('/logout', status_code=204)
async def logout(request: Request, response: Response, db=Depends(get_db)):
    _, row = await resolve_session(db, request.cookies.get(cookie_name()))
    row.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    response.delete_cookie(cookie_name(), path='/', httponly=True,
        secure=cookie_name().startswith('__Host-'), samesite='strict')
