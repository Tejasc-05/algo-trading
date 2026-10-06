"""Read models from persisted account balances, positions and fills."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database.models.paper_trading import PaperAccount, Order, Trade
from app.paper_trading.portfolio import list_open_positions


async def portfolio_summary(db, user_id):
    accounts = list((await db.execute(select(PaperAccount).where(PaperAccount.user_id == user_id))).scalars())
    positions, cash, holdings = [], 0.0, 0.0
    for account in accounts:
        cash += float(account.balance)
        for p in await list_open_positions(db, account):
            mark = float(p.last_mark_price or p.average_entry_price)
            entry, qty = float(p.average_entry_price), float(p.quantity)
            holdings += mark * qty
            pnl = (mark - entry) * qty
            positions.append(dict(id=p.id, symbol=p.symbol, side=p.side, quantity=qty,
                average_entry_price=entry, current_price=mark, pnl=pnl,
                pnl_percent=(mark / entry - 1) * 100 if entry else 0))
    trades = list((await db.execute(select(Trade).join(Order).where(Order.user_id == user_id,
        Order.paper_account_id.isnot(None)).order_by(Trade.executed_at))).scalars())
    now = datetime.now(timezone.utc)
    def dated_pnl(since):
        # Opening fees affect equity immediately. Closed-trade pnl includes those
        # fees in cost basis, so only realized values count in the daily card.
        return sum(float(t.pnl) for t in trades if t.pnl is not None and t.executed_at.replace(tzinfo=timezone.utc) >= since)
    starting = sum(float(a.starting_balance) for a in accounts)
    daily, weekly = dated_pnl(now.replace(hour=0, minute=0, second=0, microsecond=0)), dated_pnl(now - timedelta(days=7))
    total = cash + holdings
    return dict(total_value=round(total, 2), cash_balance=round(cash, 2), daily_pnl=round(daily, 2),
        daily_pnl_percent=daily / starting * 100 if starting else 0,
        weekly_pnl=round(weekly, 2), weekly_pnl_percent=weekly / starting * 100 if starting else 0,
        total_return_pct=(total / starting - 1) * 100 if starting else 0, positions=positions)


async def portfolio_performance(db, user_id):
    trades = list((await db.execute(select(Trade).join(Order).options(joinedload(Trade.order))
        .where(Order.user_id == user_id, Order.paper_account_id.isnot(None))
        .order_by(Trade.executed_at))).scalars())
    # Return a realized-profit curve. Historical market-valued account snapshots
    # are deliberately not invented from today's holdings.
    closed = [t for t in trades if t.pnl is not None]
    accounts = list((await db.execute(select(PaperAccount).where(PaperAccount.user_id == user_id))).scalars())
    total = sum(float(a.starting_balance) for a in accounts)
    curve = []
    if accounts and closed:
        curve.append(dict(date=min(a.created_at for a in accounts), value=total))
    for t in closed:
        total += float(t.pnl)
        curve.append(dict(date=t.executed_at, value=round(total, 2)))
    wins = sum(float(t.pnl) > 0 for t in closed)
    return dict(equity_curve=curve, win_rate_pct=wins / len(closed) * 100 if closed else None,
        sharpe_ratio=None, max_drawdown_pct=None)
