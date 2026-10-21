from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_user, get_db, RateLimiter, get_redis
from app.auth import account_security as service
from app.auth.sessions import cookie_name, csrf_token, issue_session, resolve_session, utc
from app.schemas.auth import PasswordRequest

router = APIRouter(prefix='/security', tags=['account-security'])


class PasswordProof(PasswordRequest):
    password: str = Field(min_length=1, max_length=128)


class CodeProof(BaseModel):
    code: str = Field(pattern=r'^\d{6}$', min_length=6, max_length=6)


class StepUp(PasswordProof, CodeProof):
    pass


class EmailProof(BaseModel):
    token: str = Field(min_length=43, max_length=128, pattern=r'^[A-Za-z0-9_-]+$')


@router.get('/status')
async def status(request: Request, user=Depends(get_current_user), db=Depends(get_db)):
    row = await service.security_row(db, user.id)
    recent = False
    if request.cookies.get(cookie_name()):
        _, session = await resolve_session(db, request.cookies[cookie_name()])
        age = (datetime.now(timezone.utc) - utc(session.mfa_at)).total_seconds() if session.mfa_at else -1
        recent = 0 <= age <= 300
    return {'email_verified': bool(row and row.email_verified_at), 'mfa_enabled': bool(row and row.mfa_secret_encrypted),
        'recent_mfa': recent, 'mfa_recovery_available': False}


@router.post('/mfa/enroll', dependencies=[Depends(RateLimiter('mfa-enroll', max_attempts=5, window_seconds=900))])
async def enroll(payload: PasswordProof, user=Depends(get_current_user), db=Depends(get_db), redis=Depends(get_redis)):
    await service.limit_user(redis, user.id, 'enroll')
    return await service.enroll(db, user.id, payload.password)


@router.post('/mfa/confirm', dependencies=[Depends(RateLimiter('mfa-confirm', max_attempts=10, window_seconds=900))])
async def confirm(payload: CodeProof, request: Request, response: Response, user=Depends(get_current_user), db=Depends(get_db), redis=Depends(get_redis)):
    await service.limit_user(redis, user.id, 'confirm', 10)
    await resolve_session(db, request.cookies.get(cookie_name()))
    user = await service.confirm_enrollment(db, user.id, payload.code, request.cookies.get(cookie_name()))
    csrf = await issue_session(db, response, user, request.cookies.get(cookie_name()), mfa=True)
    return {'message': 'Authenticator enabled. Earlier sessions have been invalidated.', 'csrf_token': csrf}


@router.post('/step-up', dependencies=[Depends(RateLimiter('mfa-step-up', max_attempts=10, window_seconds=900))])
async def step_up(payload: StepUp, request: Request, user=Depends(get_current_user), db=Depends(get_db), redis=Depends(get_redis)):
    await service.limit_user(redis, user.id, 'step-up', 10)
    await service.step_up(db, request, user.id, payload.password, payload.code)
    return {'message': 'Identity confirmed for five minutes.'}


@router.post('/email/request', status_code=202, dependencies=[Depends(RateLimiter('email-verify-request', max_attempts=5, window_seconds=900))])
async def request_email(background: BackgroundTasks, user=Depends(get_current_user), redis=Depends(get_redis)):
    from app.auth.mail import require_mail_configuration
    require_mail_configuration()
    await service.limit_user(redis, user.id, 'email', 3)
    background.add_task(service.deliver_verification, user.id)
    return {'message': 'A verification link will be sent to your account email.'}


@router.post('/email/verify', dependencies=[Depends(RateLimiter('email-verify', max_attempts=10, window_seconds=900))])
async def verify_email(payload: EmailProof, user=Depends(get_current_user), db=Depends(get_db)):
    await service.verify_email(db, user.id, payload.token)
    return {'message': 'Email address verified.'}
