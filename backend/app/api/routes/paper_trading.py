"""Owned paper accounts, controls and local simulation read models."""
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

from app.paper_trading.lifecycle import owned_account, stop_account
from app.paper_trading.account_views import snapshot
from app.paper_trading.engine import note, record_failure

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
    if not strategy.versions:
        raise AppError("INVALID_STRATEGY", "Save a strategy version first", 422)
    latest = max(strategy.versions, key=lambda v: v.version_number)
    types = {node['data']['nodeType'] for node in latest.graph_json['nodes']}
    if payload.market_type == 'spot' and types & {'openLong', 'openShort', 'closePosition'}:
        raise AppError('FUTURES_DEMO_REQUIRED', 'Choose Futures simulation for Open Long/Short actions, or use Binance Futures Demo.', 422)
    if payload.market_type == 'futures':
        if not payload.symbol.endswith('/USDT') or not types & {'openLong', 'openShort'} or types & {'buy', 'sell'}:
            raise AppError('INVALID_FUTURES_STRATEGY', 'USDT futures require Open Long/Short actions and no spot Buy/Sell actions.', 422)
        if any(n['data'].get('params', {}).get('type', 'market') != 'market' for n in latest.graph_json['nodes'] if n['data']['nodeType'] in {'openLong', 'openShort'}):
            raise AppError('FUTURES_LIMIT_UNSUPPORTED', 'Futures paper entries currently require market orders.', 422)
    elif payload.leverage != 1:
        raise AppError('INVALID_LEVERAGE', 'Spot paper accounts use 1x only.', 422)
    validation = validate_strategy_graph(StrategyGraph.model_validate(latest.graph_json))
    if not validation.valid:
        raise AppError("INVALID_STRATEGY", validation.errors[0].message, 422)
    account = PaperAccount(
        user_id=current_user.id,
        strategy_id=payload.strategy_id,
        strategy_version_id=latest.id,
        name=f"{strategy.name} · {payload.symbol} · {payload.market_type}",
        market_type=payload.market_type, leverage=payload.leverage,
        fee_rate=payload.fee_rate, slippage_rate=payload.slippage_rate,
        funding_rate=payload.funding_rate, maintenance_margin_rate=payload.maintenance_margin_rate,
        symbol=payload.symbol,
        currency=payload.symbol.split("/")[1],
        timeframe=payload.timeframe,
        starting_balance=payload.starting_balance,
        balance=payload.starting_balance,
    )
    db.add(account)
    await db.flush()
    note(account, 'WAITING_FIRST_CHECK', 'Waiting for the paper worker’s first candle check')
    await snapshot(db, account)
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
    account = await owned_account(db, current_user.id, payload.paper_account_id, lock=True)
    if not account or account.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Paper account not found")

    if not account.is_active:
        raise AppError("ACCOUNT_INACTIVE", "Paper account is inactive", 409)
    if account.market_type != "spot":
        raise AppError("FUTURES_MANUAL_ORDER_DISABLED", "Use futures strategy actions for simulated futures execution.", 422)
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
    from app.core.config import get_settings
    if get_settings().environment != 'development':
        raise AppError('SIMULATION_HELPER_DISABLED', 'Caller-supplied fill prices are available only in development.', 403)
    trade = await settle_order(db, payload.order_id, current_user.id, payload.current_price)
    order = await db.get(Order, trade.order_id)
    account = await owned_account(db, current_user.id, order.paper_account_id)
    await snapshot(db, account)
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
    close_positions: bool = False


@router.post("/stop", response_model=PaperAccountOut)
async def stop_paper_trading(
    payload: Optional[PaperTradingStopRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaperAccountOut:
    if payload and payload.paper_account_id:
        account = await owned_account(db, current_user.id, payload.paper_account_id, lock=True)
    else:
        account = (await db.execute(select(PaperAccount).where(PaperAccount.user_id == current_user.id,
            PaperAccount.is_active.is_(True)).order_by(PaperAccount.created_at.desc()).with_for_update())).scalars().first()
        if not account: raise AppError('ACCOUNT_NOT_FOUND', 'No active paper account found', 404)
    await stop_account(db, account, close_positions=bool(payload and payload.close_positions))
    return await account_view(db, account)


@router.post('/resume', response_model=PaperAccountOut)
async def resume_paper(payload: PaperTradingStopRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    account = await owned_account(db, current_user.id, payload.paper_account_id, lock=True)
    if not account.strategy_version_id:
        raise AppError('VERSION_NOT_FOUND', 'Start a new account with a saved strategy version.', 409)
    from app.paper_trading.portfolio import list_open_positions
    if float(account.balance) <= 0 and not await list_open_positions(db, account):
        raise AppError('INSUFFICIENT_BALANCE', 'Start a new account; this account has exhausted its virtual balance.', 409)
    account.is_active = True
    note(account, 'RESUMED', 'Resumed with the same saved strategy version; waiting for candle check.', last_error=None)
    await db.commit()
    return await account_view(db, account)


@router.get('/accounts', response_model=list[PaperAccountOut])
async def list_accounts(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    accounts = list((await db.execute(select(PaperAccount).where(PaperAccount.user_id == current_user.id)
        .order_by(PaperAccount.created_at.desc()))).scalars())
    return [await account_view(db, account) for account in accounts]


@router.get('/performance')
async def paper_performance(paper_account_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await owned_account(db, current_user.id, paper_account_id)
    from app.paper_trading.analytics import portfolio_performance
    return await portfolio_performance(db, current_user.id, paper_account_id)


@router.get('/positions')
async def paper_positions(paper_account_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await owned_account(db, current_user.id, paper_account_id)
    from app.paper_trading.analytics import portfolio_summary
    return (await portfolio_summary(db, current_user.id, paper_account_id))['positions']


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

    account_id = account.id
    try:
        result = await run_paper_trading_tick(
            db=db,
            account=account,
            strategy_graph=graph,
            symbol=account.symbol or "BTC/USDT",
            timeframe=account.timeframe or "1h",
        )
    except AppError as exc:
        await record_failure(db, account_id, exc.code, exc.message)
        raise
    return result


@router.get("/account", response_model=PaperAccountOut)
async def get_paper_account(
    paper_account_id: str | None = None,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> PaperAccountOut:
    if paper_account_id:
        return await account_view(db, await owned_account(db, current_user.id, paper_account_id))
    res = await db.execute(
        select(PaperAccount).where(PaperAccount.user_id == current_user.id, PaperAccount.is_active == True).order_by(PaperAccount.created_at.desc())
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

    return await account_view(db, account)


@router.get("/trades", response_model=list[PaperTradeOut])
async def list_paper_trades(
    paper_account_id: str | None = None,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[PaperTradeOut]:
    if paper_account_id: await owned_account(db, current_user.id, paper_account_id)
    res = await db.execute(
        select(Trade)
        .options(joinedload(Trade.order))
        .join(Order)
        .where(Order.user_id == current_user.id, Order.mode == TradingMode.PAPER,
            *([Order.paper_account_id == paper_account_id] if paper_account_id else []))
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
            fee=float(t.fee),
            executed_at=t.executed_at,
        )
        for t in trades
    ]
