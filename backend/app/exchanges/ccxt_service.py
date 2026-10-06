"""Concrete ExchangeInterface implementation backed by CCXT.

Supports Binance, Coinbase, Kraken, Bybit (and any other CCXT-supported
exchange). Credentials are decrypted at runtime from the Fernet-encrypted
columns in ExchangeConnection — never stored in plain text, never returned
by any API response.
"""
import asyncio
import ccxt
from datetime import datetime, timezone

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.security import decrypt_secret
from app.exchanges.base import Candle, ExchangeInterface, OrderResult, Ticker


class CCXTExchange(ExchangeInterface):
    """CCXT-backed market data. Real order execution is not implemented,
    and remains blocked even when the live-trading feature flag is set."""

    def __init__(self, exchange_id: str, api_key: str | None = None, api_secret: str | None = None,
                 passphrase: str | None = None, testnet: bool = False):
        self.exchange_id = exchange_id
        self._testnet = testnet

        # Build CCXT exchange instance
        exchange_class = getattr(ccxt, exchange_id, None)
        if exchange_id not in ccxt.exchanges or exchange_class is None:
            raise AppError(
                code="UNSUPPORTED_EXCHANGE",
                message=f"Exchange '{exchange_id}' is not supported by CCXT",
                status_code=400,
            )

        config: dict = {
            "apiKey": api_key,
            "secret": api_secret,
            "password": passphrase,
            "enableRateLimit": True,
            "timeout": 15_000,
        }
        self._exchange = exchange_class(config)
        if testnet:
            try:
                self._exchange.set_sandbox_mode(True)
            except Exception as exc:
                raise AppError("SANDBOX_UNAVAILABLE", "Exchange sandbox is unavailable", 400) from exc

    @classmethod
    def from_connection(cls, connection) -> "CCXTExchange":
        """Build a CCXTExchange from an ExchangeConnection ORM row."""
        api_key = decrypt_secret(connection.api_key_encrypted)
        api_secret = decrypt_secret(connection.api_secret_encrypted)
        passphrase = (
            decrypt_secret(connection.passphrase_encrypted)
            if connection.passphrase_encrypted
            else None
        )
        return cls(
            exchange_id=connection.exchange_name,
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            testnet=connection.is_testnet,
        )

    async def fetch_ticker(self, symbol: str) -> Ticker:
        ticker = await asyncio.to_thread(self._exchange.fetch_ticker, symbol)
        return Ticker(
            symbol=symbol,
            last_price=float(ticker["last"]),
            bid=float(ticker["bid"]) if ticker.get("bid") else None,
            ask=float(ticker["ask"]) if ticker.get("ask") else None,
            high_24h=float(ticker["high"]) if ticker.get("high") else None,
            low_24h=float(ticker["low"]) if ticker.get("low") else None,
            volume_24h=float(ticker["quoteVolume"]) if ticker.get("quoteVolume") else None,
            timestamp=datetime.fromtimestamp(ticker["timestamp"] / 1000, timezone.utc) if ticker.get("timestamp") else datetime.now(timezone.utc),
        )

    async def fetch_ohlcv(self, symbol: str, timeframe: str, since: datetime | None, limit: int) -> list[Candle]:
        since_ms = int(since.timestamp() * 1000) if since else None
        ohlcv = await asyncio.to_thread(self._exchange.fetch_ohlcv, symbol, timeframe=timeframe, since=since_ms, limit=limit)
        return [
            Candle(
                timestamp=datetime.fromtimestamp(candle[0] / 1000, timezone.utc),
                open=float(candle[1]),
                high=float(candle[2]),
                low=float(candle[3]),
                close=float(candle[4]),
                volume=float(candle[5]),
            )
            for candle in ohlcv
        ]

    async def fetch_current_price(self, symbol: str) -> float:
        ticker = await asyncio.to_thread(self._exchange.fetch_ticker, symbol)
        return float(ticker["last"])

    async def fetch_exchange_info(self) -> dict:
        markets = await asyncio.to_thread(self._exchange.load_markets)
        return {
            "exchange_id": self.exchange_id,
            "symbols": list(markets.keys()),
            "market_count": len(markets),
        }

    async def create_order(
        self, symbol: str, side: str, order_type: str, quantity: float, price: float | None = None
    ) -> OrderResult:
        settings = get_settings()
        if not settings.enable_live_trading:
            raise AppError(
                code="LIVE_TRADING_DISABLED",
                message="Live trading is disabled; real execution is not implemented.",
                status_code=403,
            )

        raise AppError(
            code="LIVE_EXECUTION_NOT_IMPLEMENTED",
            message="Real execution requires a separately reviewed execution service with risk limits and order reconciliation.",
            status_code=501,
        )
