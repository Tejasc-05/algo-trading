import os
os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///./test_check.db'
os.environ['REDIS_URL'] = 'redis://localhost:6379/0'
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

print('=== 1. REGISTER ===')
r = client.post('/api/auth/register', json={'email':'test@example.com','username':'tester','password':'Test1234!'})
print('REGISTER:', r.status_code, r.json())

if r.status_code == 200:
    token = r.json().get('access_token')
    print()
    print('=== 2. LOGIN ===')
    r2 = client.post('/api/auth/login', data={'username':'tester','password':'Test1234!'})
    print('LOGIN:', r2.status_code, r2.json())
    headers = {'Authorization': 'Bearer ' + r2.json().get('access_token')}
    print()
    print('=== 3. CREATE STRATEGY ===')
    strat = {
        'name': 'SmokeTest',
        'description': 'E2E test',
        'nodes': [
            {'id': 'data1', 'type': 'DATA', 'label': 'BTC/USDT Price', 'params': {'symbol': 'BTC/USDT', 'timeframe': '1h'}},
            {'id': 'ind1', 'type': 'INDICATOR', 'label': 'RSI', 'params': {'period': 14}},
            {'id': 'cond1', 'type': 'CONDITION', 'label': 'RSI < 30', 'params': {'operator': '<', 'threshold': 30}},
            {'id': 'act1', 'type': 'ACTION', 'label': 'BUY', 'params': {'amount': 0.01}}
        ],
        'edges': [
            {'source': 'data1', 'target': 'ind1'},
            {'source': 'ind1', 'target': 'cond1'},
            {'source': 'cond1', 'target': 'act1'}
        ]
    }
    r3 = client.post('/api/strategies', json=strat, headers=headers)
    print('CREATE STRATEGY:', r3.status_code, r3.json())
    strat_id = r3.json().get('id')
    print()
    if strat_id:
        print('=== 4. EXECUTE STRATEGY ===')
        r4 = client.post(f'/api/strategies/{strat_id}/execute', headers=headers)
        print('EXECUTE:', r4.status_code, r4.json())
        print()
        print('=== 5. LIST STRATEGIES ===')
        r5 = client.get('/api/strategies', headers=headers)
        print('LIST STRATEGIES:', r5.status_code, f'count={len(r5.json())}')
        print()
        print('=== 6. PAPER TRADING SESSIONS ===')
        r6 = client.get('/api/paper-trading/sessions', headers=headers)
        print('PAPER TRADING:', r6.status_code, r6.json())
        print()
        print('=== 7. PORTFOLIO ===')
        r7 = client.get('/api/portfolio', headers=headers)
        print('PORTFOLIO:', r7.status_code, r7.json())