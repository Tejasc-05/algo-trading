import pytest

from tests.test_api_endpoints import _create_test_strategy


@pytest.mark.asyncio
async def test_usage_tracks_owned_active_accounts(client, auth_headers):
    async def usage(headers):
        response = await client.get('/api/paper-trading/usage', headers=headers)
        assert response.status_code == 200
        return response.json()['active_bots']

    assert (await client.get('/api/paper-trading/usage')).status_code == 401
    assert await usage(auth_headers) == 0
    strategy_id = await _create_test_strategy(client, auth_headers)
    accounts = []
    for _ in range(2):
        response = await client.post('/api/paper-trading/start', headers=auth_headers,
                                     json={'strategy_id': strategy_id, 'symbol': 'BTC/USDT'})
        assert response.status_code == 201
        accounts.append(response.json()['id'])
    assert await usage(auth_headers) == 2
    other = await client.post('/api/auth/register', json={
        'email': 'other-usage@example.com', 'password': 'password123'})
    other_headers = {'Authorization': f"Bearer {other.json()['access_token']}"}
    assert await usage(other_headers) == 0
    response = await client.post('/api/paper-trading/stop', headers=auth_headers,
                                 json={'paper_account_id': accounts[0]})
    assert response.status_code == 200
    assert await usage(auth_headers) == 1
