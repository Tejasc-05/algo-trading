"""Aggregates every route module into the single /api router main.py mounts.
Adding a new feature area means adding one router module here — nothing else
in main.py needs to change."""
from fastapi import APIRouter

from app.api.routes import (
    auth,
    backtest,
    exchanges,
    market,
    paper_trading,
    portfolio,
    sentiment,
    strategies,
    users,
    futures_demo,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(strategies.router)
api_router.include_router(market.router)
api_router.include_router(backtest.router)
api_router.include_router(paper_trading.router)
api_router.include_router(exchanges.router)
api_router.include_router(portfolio.router)
api_router.include_router(sentiment.router)
api_router.include_router(futures_demo.router)
