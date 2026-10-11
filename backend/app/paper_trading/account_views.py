"""Account-specific balances, margin and equity from persisted positions."""
from datetime import datetime, timezone
from app.schemas.trading import PaperAccountOut
from app.database.models.paper_trading import PaperEquitySnapshot
from app.paper_trading.portfolio import list_open_positions
from app.paper_trading.risk import unrealized


async def account_view(db, account):
    positions = await list_open_positions(db, account)
    margin = sum(float(p.margin_balance) for p in positions) if account.market_type == 'futures' else 0
    equity = float(account.balance)
    for p in positions:
        mark = float(p.last_mark_price or p.average_entry_price)
        equity += float(p.margin_balance) + unrealized(p, mark) if account.market_type == 'futures' else float(p.quantity) * mark
    pnl = equity - float(account.starting_balance)
    return PaperAccountOut(id=account.id, name=account.name, strategy_id=account.strategy_id,
        strategy_version_id=account.strategy_version_id, market_type=account.market_type,
        leverage=account.leverage, fee_rate=float(account.fee_rate), slippage_rate=float(account.slippage_rate),
        funding_rate=float(account.funding_rate), maintenance_margin_rate=float(account.maintenance_margin_rate),
        margin_used=margin, diagnostics=account.diagnostics, currency=account.currency,
        symbol=account.symbol, timeframe=account.timeframe, balance=float(account.balance),
        starting_balance=float(account.starting_balance), equity=round(equity, 2), total_pnl=round(pnl, 2),
        total_pnl_percent=pnl / float(account.starting_balance) * 100 if account.starting_balance else 0,
        is_active=account.is_active)


async def snapshot(db, account):
    view = await account_view(db, account)
    db.add(PaperEquitySnapshot(paper_account_id=account.id,
        recorded_at=datetime.now(timezone.utc), equity=view.equity))
