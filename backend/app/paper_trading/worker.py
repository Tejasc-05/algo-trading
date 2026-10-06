"""Optional single-process paper worker; PostgreSQL locks arbitrate duplicate ticks."""
import asyncio

from sqlalchemy import select

from app.core.logging import get_logger
from app.database.database import AsyncSessionLocal
from app.database.models.paper_trading import PaperAccount
from app.database.models.strategy import StrategyVersion
from app.paper_trading.engine import run_paper_trading_tick
from app.schemas.strategy import StrategyGraph

logger = get_logger(__name__)


async def run_once():
    async with AsyncSessionLocal() as db:
        ids = list((await db.execute(select(PaperAccount.id).where(PaperAccount.is_active.is_(True)))).scalars())
    for account_id in ids:
        async with AsyncSessionLocal() as db:
            try:
                account = await db.get(PaperAccount, account_id)
                if account is None or not account.is_active or not account.strategy_version_id:
                    continue
                version = await db.get(StrategyVersion, account.strategy_version_id)
                if version:
                    await run_paper_trading_tick(db, account, StrategyGraph.model_validate(version.graph_json), account.symbol, account.timeframe)
            except Exception as exc:
                await db.rollback()
                logger.warning("Paper tick failed for account %s (%s)", account_id, type(exc).__name__)


async def main():
    while True:
        await run_once()
        await asyncio.sleep(15)


if __name__ == "__main__":
    asyncio.run(main())
