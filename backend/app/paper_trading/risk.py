"""OHLC-based exits. Intrabar sequence is unknown: choose the adverse exit first."""
from app.database.models.enums import PositionSide


def unrealized(position, price):
    direction = 1 if position.side == PositionSide.LONG else -1
    return direction * (price - float(position.average_entry_price)) * float(position.quantity)


def liquidation_price(position, maintenance_rate, fee_rate):
    """Approximation: margin + P/L equals maintenance notional + closing fee."""
    qty, entry = float(position.quantity), float(position.average_entry_price)
    margin = float(position.margin_balance)
    reserve = maintenance_rate + fee_rate
    if position.side == PositionSide.LONG:
        return max(0, (entry - margin / qty) / (1 - reserve))
    return (entry + margin / qty) / (1 + reserve)


def protective_exit(position, candle, *, liquidation=None):
    long = position.side == PositionSide.LONG
    open_, high, low = (float(candle[k]) for k in ('open', 'high', 'low'))
    adverse = []
    stop = float(position.stop_loss) if position.stop_loss is not None else None
    profit = float(position.take_profit) if position.take_profit is not None else None
    if stop is not None and (low <= stop if long else high >= stop):
        adverse.append(('STOP_LOSS', stop))
    if liquidation is not None and (low <= liquidation if long else high >= liquidation):
        adverse.append(('LIQUIDATED', liquidation))
    if adverse:
        # The nearer adverse threshold is hit first; a gap uses the opening price.
        reason, threshold = sorted(adverse, key=lambda x: x[1], reverse=long)[0]
        if liquidation is not None and (open_ <= liquidation if long else open_ >= liquidation):
            reason, threshold = 'LIQUIDATED', liquidation
        return reason, min(open_, threshold) if long else max(open_, threshold)
    if profit is not None and (high >= profit if long else low <= profit):
        return 'TAKE_PROFIT', profit  # Never assume favourable gap improvement.
    return None
