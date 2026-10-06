"""Market data endpoints — CCXT-backed ticker and OHLCV data."""
from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_current_user, get_redis
from app.redis.cache import cache_get_json, cache_set_json
from fastapi.encoders import jsonable_encoder
from app.core.exceptions import AppError
from app.database.models.user import User
from app.exchanges.ccxt_service import CCXTExchange
from app.market_data.historical import EXCHANGE_PRIORITY, fetch_latest_ohlcv
from app.schemas.market import OHLCVCandle, OHLCVResponse, TickerOut

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/ticker", response_model=TickerOut)
async def get_ticker(
    symbol: str = Query(..., min_length=3, max_length=32, examples=["BTC/USDT"]),
    current_user: User = Depends(get_current_user),
    cache=Depends(get_redis),
) -> TickerOut:
    key = f"market:ticker:{symbol}"
    try:
        cached = await cache_get_json(cache, key)
        if cached is not None:
            return TickerOut.model_validate(cached)
    except Exception:
        pass
    last_error: Exception | None = None
    for exchange_id in EXCHANGE_PRIORITY:
        try:
            exchange = CCXTExchange(exchange_id=exchange_id, testnet=False)
            ticker = await exchange.fetch_ticker(symbol)
            result = TickerOut(
                symbol=ticker.symbol,
                price=ticker.last_price,
                bid=ticker.bid,
                ask=ticker.ask,
                high_24h=ticker.high_24h,
                low_24h=ticker.low_24h,
                volume_24h=ticker.volume_24h,
                timestamp=ticker.timestamp,
            )
            try:
                await cache_set_json(cache, key, jsonable_encoder(result), ttl_seconds=5)
            except Exception:
                pass
            return result
        except Exception as exc:
            last_error = exc
            continue

    raise AppError(
        code="MARKET_DATA_UNAVAILABLE",
        message="Exchange ticker data is unavailable",
        status_code=503,
    )


@router.get("/ohlcv", response_model=list[OHLCVCandle])
async def get_ohlcv(
    symbol: str = Query(..., min_length=3, max_length=32, examples=["BTC/USDT"]),
    timeframe: str = Query("1h", examples=["1h"]),
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    cache=Depends(get_redis),
) -> list[OHLCVCandle]:
    from app.market_data.historical import TIMEFRAME_DELTA
    if timeframe not in TIMEFRAME_DELTA:
        raise AppError("INVALID_TIMEFRAME", "Unsupported timeframe", 422)
    key = f"market:candles:{symbol}:{timeframe}:{limit}"
    try:
        cached = await cache_get_json(cache, key)
        if cached is not None:
            return [OHLCVCandle.model_validate(c) for c in cached]
    except Exception:
        pass
    df = await fetch_latest_ohlcv(symbol=symbol, timeframe=timeframe, limit=limit)
    if df is None or df.empty:
        raise AppError(
            code="MARKET_DATA_UNAVAILABLE",
            message=f"No OHLCV data available for symbol '{symbol}'",
            status_code=503,
        )

    candles = [
        OHLCVCandle(
            timestamp=row.timestamp.to_pydatetime() if hasattr(row.timestamp, "to_pydatetime") else row.timestamp,
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume),
        )
        for row in df.itertuples()
    ]
    try:
        await cache_set_json(cache, key, jsonable_encoder(candles), ttl_seconds=10)
    except Exception:
        pass
    return candles
