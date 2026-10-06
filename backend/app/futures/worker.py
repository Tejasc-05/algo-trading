"""Dedicated Binance demo worker. No production adapter is imported."""
import asyncio
from sqlalchemy import select
from app.core.logging import get_logger
from app.database.database import AsyncSessionLocal
from app.database.models.futures import DemoSession
from app.futures.service import run_tick

logger = get_logger(__name__)


async def run_once():
    async with AsyncSessionLocal() as db:
        ids = list((await db.execute(select(DemoSession.id).where(DemoSession.status == 'running'))).scalars())
    for session_id in ids:
        async with AsyncSessionLocal() as db:
            try:
                session = await db.get(DemoSession, session_id)
                if session:
                    await run_tick(db, session)
            except Exception as exc:
                await db.rollback()
                logger.warning('Demo session %s paused or busy (%s)', session_id, type(exc).__name__)


async def main():
    while True:
        await run_once()
        await asyncio.sleep(15)


if __name__ == '__main__':
    asyncio.run(main())
