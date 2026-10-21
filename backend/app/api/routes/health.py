"""Unauthenticated liveness/readiness probe — used by the Docker Compose
healthcheck and for manually verifying the stack came up correctly."""
import redis.asyncio as redis
from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db), redis_client: redis.Redis = Depends(get_redis)) -> dict:
    db_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception:  # health checks must report status, never raise
        db_ok = False

    redis_ok = True
    try:
        redis_ok = bool(await redis_client.ping())
    except Exception:
        redis_ok = False

    return {"success": db_ok and redis_ok, "database": db_ok, "redis": redis_ok}


@router.get('/health/live')
async def liveness():
    return {'success': True}


@router.get('/health/ready')
async def readiness(response: Response, db: AsyncSession = Depends(get_db), redis_client=Depends(get_redis)):
    from pathlib import Path
    from alembic.script import ScriptDirectory
    ready = False
    try:
        expected = set(ScriptDirectory(str(Path(__file__).resolve().parents[3] / 'alembic')).get_heads())
        actual = set((await db.execute(text('SELECT version_num FROM alembic_version'))).scalars())
        ready = actual == expected and bool(await redis_client.ping())
    except Exception:
        await db.rollback()
    response.status_code = 200 if ready else 503
    # This is deployment readiness, not a permission to trade.
    return {'success': ready}
