from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.dependencies import get_current_user, get_db
from app.core.exceptions import AppError
from app.database.models.exchange_connection import ExchangeConnection
from app.database.models.futures import DemoOrder, DemoSession
from app.futures.binance_demo import BinanceDemo, decimal
from app.futures.service import create_session, run_tick, verify_connection

router = APIRouter(prefix='/futures-demo', tags=['binance-futures-demo'])


class ActivateDemo(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    connection_id: str
    strategy_id: str
    symbol: Literal['BTCUSDT', 'ETHUSDT'] = 'BTCUSDT'
    timeframe: Literal['1m', '5m', '15m', '1h'] = '1h'
    max_notional: float = Field(default=250, gt=0, le=1000)
    loss_limit: float = Field(default=25, gt=0, le=100)
    confirm_demo: Literal[True]


def view(session):
    return {'id': session.id, 'connection_id': session.connection_id, 'strategy_version_id': session.strategy_version_id,
        'symbol': session.symbol, 'timeframe': session.timeframe, 'status': session.status,
        'max_notional': float(session.max_notional), 'loss_limit': float(session.loss_limit),
        'starting_equity': float(session.starting_equity), 'message': session.message,
        'last_bar': session.last_bar, 'environment': 'binance_demo', 'leverage': 1}


async def owned_session(db, user_id, session_id):
    session = await db.scalar(select(DemoSession).where(DemoSession.id == session_id, DemoSession.user_id == user_id))
    if session is None:
        raise AppError('DEMO_NOT_FOUND', 'Demo session not found', 404)
    return session


@router.post('/connections/{connection_id}/verify')
async def verify_demo(connection_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    connection = await db.scalar(select(ExchangeConnection).where(
        ExchangeConnection.id == connection_id, ExchangeConnection.user_id == user.id))
    if connection is None:
        raise AppError('CONNECTION_NOT_FOUND', 'Connection not found', 404)
    account = await verify_connection(BinanceDemo(connection))
    return {'environment': 'binance_demo', 'authenticated': True, 'account_can_trade': True,
        'key_trade_permission_verified': False, 'available_balance': float(decimal(account['availableBalance'])),
        'equity': float(decimal(account['totalMarginBalance'])), 'production_execution_enabled': False}


@router.post('/sessions', status_code=201)
async def activate(payload: ActivateDemo, user=Depends(get_current_user), db=Depends(get_db)):
    return view(await create_session(db, user.id, payload))


@router.get('/sessions')
async def sessions(user=Depends(get_current_user), db=Depends(get_db)):
    rows = (await db.execute(select(DemoSession).where(DemoSession.user_id == user.id).order_by(DemoSession.created_at.desc()))).scalars()
    return [view(session) for session in rows]


@router.post('/sessions/{session_id}/tick')
async def tick(session_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    return view(await run_tick(db, await owned_session(db, user.id, session_id)))


@router.post('/sessions/{session_id}/stop')
async def stop(session_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    return view(await run_tick(db, await owned_session(db, user.id, session_id), stop=True))


@router.post('/sessions/{session_id}/resume')
async def resume(session_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    session = await owned_session(db, user.id, session_id)
    if session.status not in {'paused', 'needs_attention'}:
        raise AppError('DEMO_RESUME_STATE', 'Only paused sessions can be resumed. Stopped sessions require a new activation.', 409)
    return view(await run_tick(db, session, resume=True))


@router.get('/sessions/{session_id}/orders')
async def orders(session_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    await owned_session(db, user.id, session_id)
    rows = (await db.execute(select(DemoOrder).where(DemoOrder.session_id == session_id).order_by(DemoOrder.created_at.desc()))).scalars()
    return [{'client_id': row.client_id, 'role': row.role, 'state': row.state, 'result': row.result, 'created_at': row.created_at} for row in rows]
