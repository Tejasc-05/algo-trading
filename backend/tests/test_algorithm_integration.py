import copy

import pytest
from sqlalchemy import select

from app.database.models.exchange_connection import ExchangeConnection
from app.database.models.paper_trading import PaperAccount
from tests.test_strategy_templates import TEMPLATES

pytestmark = pytest.mark.asyncio


async def test_edited_graph_persists_and_drives_signal_and_pinned_account(client, auth_headers, db_session):
    graph = copy.deepcopy(TEMPLATES[1]['graph'])
    edits = {'rsi': {'period': 10}, 'entry': {'operator': '<', 'value': 100},
             'buy': {'amount': 0.004, 'type': 'market'}, 'stop': {'percent': 3}, 'profit': {'percent': 7}}
    for node in graph['nodes']:
        node['data']['params'] = edits.get(node['id'], node['data']['params'])
    checked = await client.post('/api/strategies/validate-graph', headers=auth_headers, json=graph)
    assert checked.status_code == 200 and checked.json()['valid']
    saved = await client.post('/api/strategies', headers=auth_headers, json={'name': 'Edited algorithm', 'graph': graph})
    assert saved.status_code == 201
    strategy = saved.json()
    fetched = await client.get(f"/api/strategies/{strategy['id']}", headers=auth_headers)
    restored = fetched.json()['versions'][0]['graph']
    assert restored['nodes'] == graph['nodes']
    assert restored['edges'] == graph['edges']
    executed = await client.post(f"/api/strategies/{strategy['id']}/execute", headers=auth_headers)
    assert executed.status_code == 200
    signals = {signal['action']: signal['params'] for signal in executed.json()['signals']}
    assert signals['buy']['amount'] == 0.004
    assert signals['set_stop_loss']['percent'] == 3
    assert signals['set_take_profit']['percent'] == 7
    started = await client.post('/api/paper-trading/start', headers=auth_headers, json={'strategy_id': strategy['id'], 'symbol': 'BTC/USDT'})
    assert started.status_code == 201
    account = await db_session.get(PaperAccount, started.json()['id'])
    assert account.strategy_version_id == strategy['versions'][0]['id']
    graph['nodes'][0]['data']['params']['period'] = 20
    updated = await client.put(f"/api/strategies/{strategy['id']}", headers=auth_headers, json={'graph': graph})
    assert updated.status_code == 200
    await db_session.refresh(account)
    assert account.strategy_version_id == strategy['versions'][0]['id']


async def test_unsaved_graph_validation_rejects_broken_wiring(client, auth_headers):
    graph = copy.deepcopy(TEMPLATES[1]['graph'])
    graph['edges'] = []
    response = await client.post('/api/strategies/validate-graph', json=graph, headers=auth_headers)
    assert response.status_code == 200
    assert not response.json()['valid']
    assert (await client.post('/api/strategies/validate-graph', json=graph)).status_code == 401


async def test_exchange_keys_are_encrypted_private_and_not_authenticated_by_public_ticker(client, auth_headers, db_session):
    payload = {'exchange_name': 'binance', 'api_key': 'qa-placeholder-key', 'api_secret': 'qa-placeholder-secret', 'is_testnet': True}
    response = await client.post('/api/exchanges/connect', headers=auth_headers, json=payload)
    assert response.status_code == 201
    connection_id = response.json()['id']
    assert 'qa-placeholder' not in response.text
    row = (await db_session.execute(select(ExchangeConnection).where(ExchangeConnection.id == connection_id))).scalar_one()
    assert row.api_key_encrypted != payload['api_key']
    assert row.api_secret_encrypted != payload['api_secret']
    checked = await client.post(f'/api/exchanges/{connection_id}/test', headers=auth_headers)
    assert checked.status_code == 200
    assert checked.json()['market_data_reachable'] is True
    assert checked.json()['credentials_verified'] is False
    other = await client.post('/api/auth/register', json={'email': 'exchange-isolation@example.com', 'password': 'password123'})
    other_headers = {'Authorization': f"Bearer {other.json()['access_token']}"}
    assert (await client.get('/api/exchanges', headers=other_headers)).json() == []
    for method, suffix in [('POST', '/test'), ('DELETE', '')]:
        denied = await client.request(method, f'/api/exchanges/{connection_id}{suffix}', headers=other_headers)
        assert denied.status_code == 404
