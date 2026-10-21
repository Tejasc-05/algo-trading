from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import get_current_user, get_db, get_redis, RateLimiter
from app.auth.account_security import require_live_user, security_row, limit_user
from app.auth.sessions import cookie_name, resolve_session, utc
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.database.models.exchange_connection import ExchangeConnection
from app.database.models.live import LiveAccount
from app.live.binance_readonly import BinanceReadOnly

router = APIRouter(prefix='/live', tags=['live-readiness'])


@router.get('/readiness')
async def readiness(request: Request, user=Depends(get_current_user), db=Depends(get_db)):
    security = await security_row(db, user.id)
    recent = False
    if request.cookies.get(cookie_name()):
        _, session = await resolve_session(db, request.cookies[cookie_name()])
        age = (datetime.now(timezone.utc) - utc(session.mfa_at)).total_seconds() if session.mfa_at else -1
        recent = 0 <= age <= 300
    checks = [
        ('email_verified', bool(security and security.email_verified_at), 'Verify your account email in Settings.'),
        ('mfa_enabled', bool(security and security.mfa_secret_encrypted), 'Enable an authenticator app in Settings.'),
        ('recent_mfa', recent, 'Confirm identity with a fresh authenticator code before live actions.'),
        ('mfa_recovery', False, 'Secure recovery for a lost authenticator must be completed before public release.'),
        ('production_deployment', get_settings().environment == 'production', 'Use the reviewed HTTPS production deployment.'),
        ('execution_service', False, 'Production orchestration, risk monitoring and recovery are incomplete; the internal ledger does not enable orders.'),
        ('exchange_acceptance', False, 'A genuine demo order lifecycle and recovery test must be recorded before release.'),
        ('operations_acceptance', False, 'Jurisdiction eligibility, alerts, backup restore and deployment acceptance remain required.'),
    ]
    return {'ready': False, 'exchange': 'binance_usdm', 'production_orders_enabled': False,
        'checks': [{'key': key, 'passed': passed, 'message': message} for key, passed, message in checks]}


def account_view(row):
    return {'id': row.id, 'connection_id': row.connection_id, 'verified_at': row.verified_at,
        'environment': 'binance_production', 'execution_enabled': False}


@router.get('/accounts')
async def accounts(user=Depends(get_current_user), db=Depends(get_db)):
    rows = (await db.execute(select(LiveAccount).where(LiveAccount.user_id == user.id))).scalars()
    return [account_view(row) for row in rows]


@router.post('/connections/{connection_id}/verify', dependencies=[Depends(RateLimiter('live-verification', max_attempts=5, window_seconds=900))])
async def verify(connection_id: str, request: Request, user=Depends(get_current_user), db=Depends(get_db), redis=Depends(get_redis)):
    await require_live_user(db, request, user)
    await limit_user(redis, user.id, 'live-verify', 5)
    connection = await db.scalar(select(ExchangeConnection).where(
        ExchangeConnection.id == connection_id, ExchangeConnection.user_id == user.id).with_for_update())
    if connection is None:
        raise AppError('CONNECTION_NOT_FOUND', 'Connection not found.', 404)
    result = await BinanceReadOnly(connection).verify()
    row = await db.scalar(select(LiveAccount).where(LiveAccount.account_identity == result['account_identity']).with_for_update())
    if row is not None and row.user_id != user.id:
        raise AppError('LIVE_ACCOUNT_ALREADY_REGISTERED', 'This Binance account is already registered to another AlgoFlow user.', 409)
    if row is None:
        row = LiveAccount(user_id=user.id, account_identity=result['account_identity'])
        db.add(row)
    row.connection_id = connection.id
    row.verified_at = datetime.now(timezone.utc)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise AppError('LIVE_ACCOUNT_CONFLICT', 'The account was registered concurrently. Refresh and try again.', 409) from None
    return {**account_view(row), 'authenticated': True, 'permissions_verified': True,
        'message': 'Read-only verification passed. No order was placed and live execution remains unavailable.'}
