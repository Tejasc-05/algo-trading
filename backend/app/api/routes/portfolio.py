from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_current_user, get_db
from app.database.models.user import User
from app.schemas.trading import PortfolioOut, PortfolioPerformanceOut
from app.paper_trading.analytics import portfolio_summary, portfolio_performance

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

@router.get("", response_model=PortfolioOut)
async def get_portfolio(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await portfolio_summary(db, current_user.id)

@router.get("/performance", response_model=PortfolioPerformanceOut)
async def get_portfolio_performance(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await portfolio_performance(db, current_user.id)
