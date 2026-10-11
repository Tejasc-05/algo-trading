"""Optional single-process paper worker; PostgreSQL locks arbitrate duplicate ticks."""
import asyncio

from sqlalchemy import select

from app.core.logging import get_logger
from app.database.database import AsyncSessionLocal
from app.database.models.paper_trading import PaperAccount
from app.database.models.strategy import StrategyVersion
from app.paper_trading.engine import run_paper_trading_tick, record_failure
from app.core.exceptions import AppError
from app.schemas.strategy import StrategyGraph

logger = get_logger(__name__)


async def run_once():
    async with AsyncSessionLocal() as db:
        ids = list((await db.execute(select(PaperAccount.id).where(PaperAccount.is_active.is_(True)))).scalars())
    for account_id in ids:
        async with AsyncSessionLocal() as db:
            try:
                account = await db.get(PaperAccount, account_id)
                if account is None or not account.is_active:
                    continue
                if not account.strategy_version_id:
                    raise AppError('VERSION_NOT_FOUND', 'Paper account has no pinned strategy version; start a new account.', 409)
                version = await db.get(StrategyVersion, account.strategy_version_id)
                if not version:
                    raise AppError('VERSION_NOT_FOUND', 'The pinned strategy version is unavailable; start a new account.', 409)
                if version:
                    await run_paper_trading_tick(db, account, StrategyGraph.model_validate(version.graph_json), account.symbol, account.timeframe)
            except Exception as exc:
                await record_failure(db, account_id,
                    exc.code if isinstance(exc, AppError) else 'WORKER_ERROR',
                    exc.message if isinstance(exc, AppError) else 'Paper worker could not complete the candle check.')
                logger.warning("Paper tick failed for account %s (%s)", account_id, type(exc).__name__)


async def main():
    while True:
        await run_once()
        await asyncio.sleep(15)


if __name__ == "__main__":
    asyncio.run(main())
