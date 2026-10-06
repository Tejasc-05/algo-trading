"""Account response mapping includes held assets rather than cash-only P/L."""
from app.schemas.trading import PaperAccountOut
from app.paper_trading.portfolio import list_open_positions


async def account_view(db, account):
    positions = await list_open_positions(db, account)
    equity = float(account.balance) + sum(
        float(p.quantity) * float(p.last_mark_price or p.average_entry_price) for p in positions)
    pnl = equity - float(account.starting_balance)
    return PaperAccountOut(id=account.id, strategy_id=account.strategy_id, currency=account.currency,
        symbol=account.symbol, timeframe=account.timeframe, balance=float(account.balance),
        starting_balance=float(account.starting_balance), equity=round(equity, 2), total_pnl=round(pnl, 2),
        total_pnl_percent=pnl / float(account.starting_balance) * 100 if account.starting_balance else 0,
        is_active=account.is_active)
