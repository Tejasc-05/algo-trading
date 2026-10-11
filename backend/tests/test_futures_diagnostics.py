"""Explanations must use actual outputs, preserve execution, and respect ownership."""
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select
from app.database.models.futures import DemoSession
from app.schemas.strategy import StrategyGraph
from app.strategy_engine.executor import StrategyExecutor
from app.strategy_engine.indicators import macd
from tests.test_futures_demo import FakeDemo, activate, reset_fake

FUTURES = json.loads((Path(__file__).resolve().parents[2]/'src/features/strategy-builder/futures-templates.json').read_text())


def test_trace_matches_actual_macd_and_does_not_change_signals():
    graph = StrategyGraph.model_validate(FUTURES[0]['graph'])
    executor = StrategyExecutor(graph)
    context = {'candles':pd.DataFrame({'close':np.r_[np.linspace(180,100,80),np.linspace(100,230,80)]})}
    plain = executor.evaluate(context)
    trace = []
    traced = executor.evaluate(context, trace=trace)
    assert plain == traced
    indicator = next(row for row in trace if row['id']=='macd')
    expected = macd(context['candles']['close'],12,26,9)
    for key in ('macd','signal','histogram'):
        assert indicator['macd'][key]['current']==pytest.approx(expected[key].iloc[-1])
        assert indicator['macd'][key]['previous']==pytest.approx(expected[key].iloc[-2])
    condition = next(row for row in trace if row['id']=='entry')
    assert condition['current'] is True
    assert condition['inputs'][0]['current']==indicator['macd']['histogram']['current']
    assert next(row for row in trace if row['node_type']=='openLong')['triggered']
    # Trace reused on the next call cannot retain prior values or non-JSON NaN.
    executor.evaluate({'candles':pd.DataFrame({'close':[100.]*5})},trace=trace)
    assert len(trace)==len(graph.nodes)
    assert next(row for row in trace if row['id']=='macd')['current'] is None
    assert next(row for row in trace if row['id']=='entry')['current'] is None
    assert not next(row for row in trace if row['node_type']=='openLong')['triggered']
    json.dumps(trace,allow_nan=False)


@pytest.mark.asyncio
async def test_no_entry_snapshot_and_same_bar_retains_evaluation(client,auth_headers,monkeypatch,db_session):
    session,payload=await activate(client,auth_headers,monkeypatch)
    stored=await db_session.get(DemoSession,session['id'])
    from app.database.models.strategy import StrategyVersion
    version=await db_session.get(StrategyVersion,stored.strategy_version_id)
    graph=copy.deepcopy(version.graph_json)
    graph['nodes'][1]['data']['params']['value']=0  # RSI < 0 cannot produce entry
    version.graph_json=graph
    await db_session.commit()
    url=f"/api/futures-demo/sessions/{session['id']}"
    first=await client.post(url+'/tick',headers=auth_headers)
    assert first.status_code==200,first.text
    data=first.json()['diagnostics']
    assert data['reason_code']=='NO_ENTRY_SIGNAL'
    assert data['evaluation']['entry_signals']==[]
    assert data['evaluation']['bars_used']==100  # unfinished candle excluded
    candle=datetime.fromisoformat(data['evaluation']['candle_close_at'])
    assert candle < datetime.now(timezone.utc)
    assert data['evaluation']['strategy_version_id']==session['strategy_version_id']
    assert data['position']['side']=='flat'
    assert FakeDemo.calls==[]
    # Duplicate bar only updates runner heartbeat, not the evaluated candle or orders.
    async def same_candles(self, method,path,params=None,signed=False):
        if path.endswith('/klines'):
            start=int(datetime.fromisoformat(data['evaluation']['candle_open_at']).timestamp()*1000)
            return [[start,'100','101','99','100','10',int(candle.timestamp()*1000)]]
        return await original(self,method,path,params,signed)
    original=FakeDemo.request
    monkeypatch.setattr(FakeDemo,'request',same_candles)
    second=await client.post(url+'/tick',headers=auth_headers)
    assert second.status_code==200,second.text
    assert second.json()['diagnostics']['reason_code']=='WAITING_NEXT_CANDLE'
    assert second.json()['diagnostics']['evaluation']==data['evaluation']
    assert FakeDemo.calls==[]
    assert (await client.get('/api/futures-demo/sessions',headers=auth_headers)).json()[0]['diagnostics']['evaluation']==data['evaluation']
    other=await client.post('/api/auth/register',json={'email':'diagnostics-other@example.com','password':'password123'})
    headers={'Authorization':'Bearer '+other.json()['access_token']}
    assert (await client.get('/api/futures-demo/sessions',headers=headers)).json()==[]


@pytest.mark.asyncio
async def test_blocking_limits_survive_rollback_without_orders(client,auth_headers,monkeypatch):
    session,_=await activate(client,auth_headers,monkeypatch,quantity=5)
    response=await client.post(f"/api/futures-demo/sessions/{session['id']}/tick",headers=auth_headers)
    assert response.status_code==422
    current=(await client.get('/api/futures-demo/sessions',headers=auth_headers)).json()[0]
    snapshot=current['diagnostics']
    assert snapshot['reason_code']=='DEMO_RISK_LIMIT' and current['status']=='needs_attention'
    assert snapshot['evaluation']['entry_signals']
    assert float(snapshot['entry_limits']['notional'])==500
    assert snapshot['last_error']['code']=='DEMO_RISK_LIMIT'
    assert FakeDemo.calls==[]


@pytest.mark.asyncio
async def test_snapshot_reports_confirmed_fill_and_flat_after_stop(client,auth_headers,monkeypatch):
    session,_=await activate(client,auth_headers,monkeypatch,short=True)
    url=f"/api/futures-demo/sessions/{session['id']}"
    filled=await client.post(url+'/tick',headers=auth_headers)
    assert filled.status_code==200,filled.text
    data=filled.json()['diagnostics']
    assert data['reason_code']=='ENTRY_FILLED' and data['position']['side']=='short'
    stopped=await client.post(url+'/stop',headers=auth_headers)
    assert stopped.json()['diagnostics']['reason_code']=='STOPPED'
    assert stopped.json()['diagnostics']['position']['side']=='flat'
