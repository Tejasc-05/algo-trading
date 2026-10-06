"""Minimal paper trading endpoints for the MVP.

These routes implement a lightweight paper account + order creation API and a
developer helper to materialize fills deterministically. The full production
engine (background processing, realtime events, advanced matching) is
implemented in later phases.
"""
from datetime import datetime, timezone
from typing import Optional, Literal

from fastapi import APIRouter, Depends, status, HTTPException
from pydantic import BaseModel, Field, ConfigDict, model_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload

from app.api.dependencies import get_current_user, get_db
from app.database.models.user import User
from app.database.models.paper_trading import PaperAccount, Order, Trade
from app.schemas.trading import PaperAccountOut, PaperTradeOut, PaperTradingStartRequest
from app.database.models.enums import TradingMode, OrderStatus
from app.paper_trading.service import settle_order
from app.paper_trading.account_views import account_view
from app.core.exceptions import AppError
from app.database.repositories.strategy_repository import StrategyRepository

router = APIRouter(prefix="/paper-trading", tags=["paper-trading"])


class PaperUsageOut(BaseModel):
    active_bots: int


@router.get("/usage", response_model=PaperUsageOut)
async def get_paper_usage(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> PaperUsageOut:
    count = await db.scalar(
        select(func.count(PaperAccount.id)).where(
            PaperAccount.user_id == current_user.id,
            PaperAccount.is_active.is_(True),
            PaperAccount.strategy_id.is_not(None),
        )
    )
    return PaperUsageOut(active_bots=count or 0)


@router.post("/start", response_model=PaperAccountOut, status_code=status.HTTP_201_CREATED)
async def start_paper_trading(
    payload: PaperTradingStartRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> PaperAccountOut:
    strategy = await StrategyRepository(db).get_with_versions(payload.strategy_id)
    if strategy is None or strategy.user_id != current_user.id:
        raise AppError("STRATEGY_NOT_FOUND", "Strategy not found", 404)
    from app.schemas.strategy import StrategyGraph
    from app.strategy_engine.validator import validate_strategy_graph
    latest = max(strategy.versions, key=lambda v: v.version_number)
    if any(node['data']['nodeType'] in {'openLong', 'openShort', 'closePosition'} for node in latest.graph_json['nodes']):
        raise AppError('FUTURES_DEMO_REQUIRED', 'Use Binance Futures Demo for futures actions; paper accounts are spot only.', 422)
    validation = validate_strategy_graph(StrategyGraph.model_validate(latest.graph_json))
    if not validation.valid:
        raise AppError("INVALID_STRATEGY", validation.errors[0].message, 422)
    account = PaperAccount(
        user_id=current_user.id,
        strategy_id=payload.strategy_id,
        strategy_version_id=latest.id,
        name=f"Paper Account {payload.strategy_id}",
        symbol=payload.symbol,
        currency=payload.symbol.split("/")[1],
        timeframe=payload.timeframe,
        starting_balance=payload.starting_balance,
        balance=payload.starting_balance,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)

    return await account_view(db, account)


class PaperOrderIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    paper_account_id: str
    symbol: str
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"]
    quantity: float = Field(gt=0)
    price: Optional[float] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_limit(self):
        if self.order_type == "limit" and self.price is None:
            raise ValueError("A limit order requires price")
        return self


@router.post("/orders", status_code=status.HTTP_201_CREATED)
async def create_paper_order(
    payload: PaperOrderIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # ensure account belongs to user
    res = await db.execute(select(PaperAccount).where(PaperAccount.id == payload.paper_account_id))
    account = res.scalars().first()
    if not account or account.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Paper account not found")

    if not account.is_active:
        raise AppError("ACCOUNT_INACTIVE", "Paper account is inactive", 409)
    if payload.symbol != account.symbol:
        raise AppError("SYMBOL_MISMATCH", "Order symbol must match paper account", 422)
    order = Order(
        user_id=current_user.id,
        strategy_id=account.strategy_id,
        paper_account_id=account.id,
        mode=TradingMode.PAPER,
        symbol=payload.symbol,
        side=payload.side,
        order_type=payload.order_type,
        quantity=payload.quantity,
        price=payload.price,
        status=OrderStatus.PENDING,
    )

    db.add(order)
    await db.commit()
    await db.refresh(order)

    return {"order_id": order.id, "status": order.status}


class SimulateFillIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    order_id: str
    current_price: float = Field(gt=0)


@router.post("/simulate-fill", status_code=status.HTTP_200_OK)
async def simulate_fill_endpoint(
    payload: SimulateFillIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    trade = await settle_order(db, payload.order_id, current_user.id, payload.current_price)
    await db.commit()
    await db.refresh(trade)

    from app.redis.pubsub import publish_user_event
    await publish_user_event(current_user.id, "paper_order", {
        "order_id": trade.order_id, "executed_price": float(trade.executed_price),
        "executed_quantity": float(trade.executed_quantity), "fee": float(trade.fee),
    })

    return {
        "trade_id": trade.id,
        "order_id": trade.order_id,
        "executed_price": float(trade.executed_price),
        "executed_quantity": float(trade.executed_quantity),
        "fee": float(trade.fee),
    }


class PaperTradingStopRequest(BaseModel):
    paper_account_id: Optional[str] = None


@router.post("/stop", response_model=PaperAccountOut)
async def stop_paper_trading(
    payload: Optional[PaperTradingStopRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaperAccountOut:
    stmt = select(PaperAccount).where(PaperAccount.user_id == current_user.id, PaperAccount.is_active == True)
    if payload and payload.paper_account_id:
        stmt = stmt.where(PaperAccount.id == payload.paper_account_id)
    res = await db.execute(stmt)
    account = res.scalars().first()
    if not account:
        raise HTTPException(status_code=404, detail="No active paper account found")

    account.is_active = False
    await db.commit()
    await db.refresh(account)

    pnl = float(account.balance) - float(account.starting_balance)
    pnl_percent = (pnl / float(account.starting_balance) * 100) if float(account.starting_balance) else 0.0

    return await account_view(db, account)


class PaperTradingTickRequest(BaseModel):
    paper_account_id: Optional[str] = None


@router.post("/tick")
async def run_paper_tick(
    payload: Optional[PaperTradingTickRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.database.repositories.strategy_repository import StrategyRepository
    from app.schemas.strategy import StrategyGraph
    from app.paper_trading.engine import run_paper_trading_tick

    stmt = select(PaperAccount).where(PaperAccount.user_id == current_user.id, PaperAccount.is_active == True)
    if payload and payload.paper_account_id:
        stmt = stmt.where(PaperAccount.id == payload.paper_account_id)
    res = await db.execute(stmt)
    account = res.scalars().first()
    if not account:
        raise HTTPException(status_code=404, detail="No active paper account found")

    if not account.strategy_id:
        raise HTTPException(status_code=400, detail="Account has no associated strategy")

    repo = StrategyRepository(db)
    # Use eager‑loading to include strategy versions and avoid lazy‑load errors in async context
    strategy = await repo.get_with_versions(account.strategy_id)
    if not strategy or strategy.user_id != current_user.id or not strategy.versions:
        raise HTTPException(status_code=404, detail="Strategy not found")

    latest_version = next((v for v in strategy.versions if v.id == account.strategy_version_id), None)
    if latest_version is None:
        raise AppError("VERSION_NOT_FOUND", "Paper account has no pinned strategy version; start a new account", 409)
    graph = StrategyGraph.model_validate(latest_version.graph_json)

    result = await run_paper_trading_tick(
        db=db,
        account=account,
        strategy_graph=graph,
        symbol=account.symbol or "BTC/USDT",
        timeframe=account.timeframe or "1h",
    )
    return result


@router.get("/account", response_model=PaperAccountOut)
async def get_paper_account(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> PaperAccountOut:
    res = await db.execute(
        select(PaperAccount).where(PaperAccount.user_id == current_user.id, PaperAccount.is_active == True)
    )
    account = res.scalars().first()
    if not account:
        res2 = await db.execute(
            select(PaperAccount)
            .where(PaperAccount.user_id == current_user.id)
            .order_by(PaperAccount.created_at.desc())
        )
        account = res2.scalars().first()
        if not account:
            raise HTTPException(status_code=404, detail="No paper account found")

    pnl = float(account.balance) - float(account.starting_balance)
    pnl_percent = (pnl / float(account.starting_balance) * 100) if float(account.starting_balance) else 0.0

    return await account_view(db, account)


@router.get("/trades", response_model=list[PaperTradeOut])
async def list_paper_trades(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[PaperTradeOut]:
    res = await db.execute(
        select(Trade)
        .options(joinedload(Trade.order))
        .join(Order)
        .where(Order.user_id == current_user.id)
        .order_by(Trade.executed_at.desc())
    )
    trades = res.scalars().all()
    return [
        PaperTradeOut(
            id=t.id,
            symbol=t.order.symbol,
            side=t.order.side.value if hasattr(t.order.side, "value") else str(t.order.side),
            status=t.order.status.value if hasattr(t.order.status, "value") else str(t.order.status),
            quantity=float(t.executed_quantity),
            price=float(t.executed_price),
            pnl=float(t.pnl) if t.pnl is not None else None,
            executed_at=t.executed_at,
        )
        for t in trades
    ]
