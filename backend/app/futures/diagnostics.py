"""Observed demo decisions only. Never calls the exchange or changes signals."""
from datetime import datetime, timezone
from app.market_data.historical import TIMEFRAME_DELTA
from app.strategy_engine.diagnostics import scalar


def note(session, code, reason, **facts):
    session.diagnostics = {**(session.diagnostics or {}), 'schema_version': 1,
        'checked_at': datetime.now(timezone.utc).isoformat(), 'reason_code': code, 'reason': reason, **facts}


def evaluation(session, trace, signals, closed, version_number):
    bar = closed[-1]
    opens = [signal.action for signal in signals if signal.action in {'buy', 'openLong', 'openShort'}]
    exits = [signal.action for signal in signals if signal.action in {'sell', 'closePosition'}]
    return {'evaluated_at': datetime.now(timezone.utc).isoformat(),
        'candle_open_at': datetime.fromtimestamp(int(bar[0])/1000, timezone.utc).isoformat(),
        'candle_close_at': datetime.fromtimestamp(int(bar[6])/1000, timezone.utc).isoformat(),
        'next_candle_close_at': (datetime.fromtimestamp((int(bar[6])+1)/1000, timezone.utc)+TIMEFRAME_DELTA[session.timeframe]).isoformat(),
        'strategy_version_id': session.strategy_version_id, 'strategy_version_number': version_number,
        'bars_used': len(closed), 'close_price': scalar(float(bar[4])), 'nodes': trace,
        'entry_signals': opens, 'exit_signals': exits,
        'decision': 'Entry signal produced' if opens else 'No entry signal on this candle'}
