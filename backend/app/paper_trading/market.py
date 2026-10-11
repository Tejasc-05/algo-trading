"""Public Binance USD-M candles only. No credentials or trading endpoints."""
import asyncio
from app.core.exceptions import AppError
from app.exchanges.ccxt_service import CCXTExchange
from app.market_data.historical import normalize_ohlcv


async def fetch_futures_ohlcv(symbol, timeframe, limit=120):
    try:
        exchange = CCXTExchange('binanceusdm', testnet=False)
        rows = await asyncio.to_thread(exchange._exchange.fetch_ohlcv,
            f'{symbol}:USDT', timeframe=timeframe, limit=limit)
        if not rows:
            raise ValueError('Empty candles')
        frame = normalize_ohlcv(rows)
        frame.attrs['source'] = 'Binance USD-M public contract candles'
        return frame
    except Exception as exc:
        raise AppError('MARKET_DATA_UNAVAILABLE', 'Binance futures candle data is unavailable; paper orders were not simulated.', 503) from exc
