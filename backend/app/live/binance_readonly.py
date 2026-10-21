"""Pinned-host signed reads only; no order or account-changing method exists."""
import hashlib
import hmac
from urllib.parse import urlencode

import httpx

from app.core.exceptions import AppError
from app.core.security import decrypt_secret

HOSTS = {'/sapi/v1/account/apiRestrictions': ('https://api.binance.com', '/api/v3/time'),
    **{path: ('https://fapi.binance.com', '/fapi/v1/time') for path in (
        '/fapi/v3/balance', '/fapi/v1/accountConfig', '/fapi/v1/positionSide/dual', '/fapi/v1/multiAssetsMargin')}}


class BinanceReadOnly:
    def __init__(self, connection, http=None):
        if connection.exchange_name not in {'binance', 'binanceusdm'} or connection.is_testnet or not connection.is_active:
            raise AppError('LIVE_CONNECTION_REQUIRED', 'Use an active production Binance futures connection.', 422)
        self.key = decrypt_secret(connection.api_key_encrypted)
        self.secret = decrypt_secret(connection.api_secret_encrypted)
        self.http = http

    async def _get(self, http, path):
        host, clock_path = HOSTS[path]
        try:
            clock = await http.get(host + clock_path)
            clock.raise_for_status()
            query = urlencode({'timestamp': int(clock.json()['serverTime']), 'recvWindow': 5000})
            signature = hmac.new(self.secret.encode(), query.encode(), hashlib.sha256).hexdigest()
            response = await http.get(host + path, params=query + '&signature=' + signature, headers={'X-MBX-APIKEY': self.key})
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and int(data.get('code', 0)) < 0:
                raise ValueError('exchange error')
            return data
        except (httpx.HTTPError, ValueError, KeyError, TypeError, OverflowError):
            raise AppError('LIVE_VERIFICATION_UNAVAILABLE', 'Binance verification failed. Check API permissions, IP restriction and account eligibility.', 503) from None

    async def verify(self):
        if self.http is not None:
            return await self._verify(self.http)
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as http:
            return await self._verify(http)

    async def _verify(self, http):
        permissions = await self._get(http, '/sapi/v1/account/apiRestrictions')
        required = {'enableReading': True, 'enableFutures': True, 'enableWithdrawals': False,
            'ipRestrict': True, 'enableInternalTransfer': False, 'permitsUniversalTransfer': False,
            'enableSpotAndMarginTrading': False}
        if not isinstance(permissions, dict) or any(permissions.get(key) is not value for key, value in required.items()):
            raise AppError('LIVE_KEY_PERMISSIONS', 'Use a futures-only, IP-restricted key with withdrawals and transfers disabled. Missing permission fields cannot be verified.', 422)
        config = await self._get(http, '/fapi/v1/accountConfig')
        mode = await self._get(http, '/fapi/v1/positionSide/dual')
        multi = await self._get(http, '/fapi/v1/multiAssetsMargin')
        if (not all(isinstance(value, dict) for value in (config, mode, multi)) or config.get('canTrade') is not True
                or mode.get('dualSidePosition') is not False or multi.get('multiAssetsMargin') is not False):
            raise AppError('LIVE_ACCOUNT_MODE', 'A trading-enabled one-way, single-asset futures account is required.', 422)
        balances = await self._get(http, '/fapi/v3/balance')
        aliases = set()
        if isinstance(balances, list):
            for row in balances:
                if isinstance(row, dict) and row.get('asset') == 'USDT':
                    value = row.get('accountAlias')
                    if isinstance(value, str) and value and len(value) <= 128:
                        aliases.add(value)
                    else:
                        raise AppError('LIVE_ACCOUNT_IDENTITY', 'Binance did not return a verifiable account identity.', 503)
        if len(aliases) != 1:
            raise AppError('LIVE_ACCOUNT_IDENTITY', 'Binance did not return a unique USDT futures account identity.', 503)
        alias = aliases.pop()
        if not isinstance(alias, str) or not alias or len(alias) > 128:
            raise AppError('LIVE_ACCOUNT_IDENTITY', 'Binance did not return a verifiable account identity.', 503)
        return {'account_identity': hashlib.sha256(('binance_usdm:' + alias).encode()).hexdigest(), 'permissions_verified': True}
