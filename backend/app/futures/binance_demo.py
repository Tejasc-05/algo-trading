"""Signed Binance USD-M demo transport, pinned to Binance's demo hostname.

Never accepts a caller-provided URL. Mutating requests are never retried:
unknown outcomes must be reconciled using their persisted client IDs.
"""
import hashlib
import hmac
from decimal import Decimal, ROUND_DOWN
from urllib.parse import urlencode

import httpx

from app.core.exceptions import AppError
from app.core.security import decrypt_secret

DEMO_HOST = 'https://demo-fapi.binance.com'


class DemoRequestError(AppError):
    def __init__(self, ambiguous=False, code=None):
        self.ambiguous = ambiguous
        self.exchange_code = code
        super().__init__('BINANCE_DEMO_UNAVAILABLE',
                         'Binance demo request failed; check account permissions, environment and connection.', 503)


class BinanceDemo:
    def __init__(self, connection):
        if connection.exchange_name not in {'binance', 'binanceusdm'} or not connection.is_testnet or not connection.is_active:
            raise AppError('DEMO_CONNECTION_REQUIRED', 'Use an active Binance USD-M demo connection. Production keys are not supported.', 422)
        self.key = decrypt_secret(connection.api_key_encrypted)
        self.secret = decrypt_secret(connection.api_secret_encrypted)

    async def request(self, method, path, params=None, signed=False):
        values = dict(params or {})
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            if signed:
                try:
                    clock = await client.get(DEMO_HOST + '/fapi/v1/time')
                    clock.raise_for_status()
                    values.update(timestamp=int(clock.json()['serverTime']), recvWindow=5000)
                except (httpx.HTTPError, ValueError, KeyError):
                    raise DemoRequestError() from None
            query = urlencode(values)
            if signed:
                signature = hmac.new(self.secret.encode(), query.encode(), hashlib.sha256).hexdigest()
                query += '&signature=' + signature
            try:
                headers = {'X-MBX-APIKEY': self.key} if signed else {}
                # Body for signed writes avoids credentials/signatures in URL logs.
                if method in {'POST', 'DELETE'}:
                    response = await client.request(method, DEMO_HOST + path, content=query,
                        headers={**headers, 'Content-Type': 'application/x-www-form-urlencoded'})
                else:
                    response = await client.request(method, DEMO_HOST + path, params=query, headers=headers)
                data = response.json()
            except (httpx.HTTPError, ValueError):
                raise DemoRequestError(ambiguous=method == 'POST') from None
            if response.status_code >= 400 or (isinstance(data, dict) and int(data.get('code', 0)) < 0):
                code = data.get('code') if isinstance(data, dict) else None
                raise DemoRequestError(ambiguous=method == 'POST' and
                    (response.status_code >= 500 or code in {-1006, -1007}), code=code)
            return data

    async def account(self):
        return await self.request('GET', '/fapi/v3/account', signed=True)

    async def positions(self, symbol):
        return await self.request('GET', '/fapi/v2/positionRisk', {'symbol': symbol}, signed=True)

    async def order(self, params, conditional=False):
        return await self.request('POST', '/fapi/v1/algoOrder' if conditional else '/fapi/v1/order', params, signed=True)

    async def query(self, symbol, client_id, conditional=False):
        return await self.request('GET', '/fapi/v1/algoOrder' if conditional else '/fapi/v1/order',
            {'clientAlgoId': client_id} if conditional else {'symbol': symbol, 'origClientOrderId': client_id}, signed=True)

    async def cancel(self, symbol, client_id):
        return await self.request('DELETE', '/fapi/v1/algoOrder', {'clientAlgoId': client_id}, signed=True)

    async def cancel_regular(self, symbol, client_id):
        return await self.request('DELETE', '/fapi/v1/order', {'symbol': symbol, 'origClientOrderId': client_id}, signed=True)

    async def rules(self, symbol):
        info = await self.request('GET', '/fapi/v1/exchangeInfo')
        market = next((item for item in info['symbols'] if item['symbol'] == symbol), None)
        if not market or market['status'] != 'TRADING' or market.get('contractType') != 'PERPETUAL':
            raise AppError('INVALID_DEMO_MARKET', 'Only active BTC/ETH USDT perpetual markets are supported.', 422)
        return {item['filterType']: item for item in market['filters']}


def decimal(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise AppError('INVALID_EXCHANGE_DATA', 'Exchange returned a non-finite value', 503)
    return result


def quantize_quantity(value, rules):
    rule = rules.get('MARKET_LOT_SIZE') or rules['LOT_SIZE']
    step = decimal(rule['stepSize'])
    qty = (decimal(value) / step).to_integral_value(rounding=ROUND_DOWN) * step
    if qty < decimal(rule['minQty']) or qty > decimal(rule['maxQty']):
        raise AppError('INVALID_QUANTITY', 'Quantity is outside Binance market limits.', 422)
    return qty
