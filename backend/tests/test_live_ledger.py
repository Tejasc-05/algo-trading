"""Durable intent must survive ambiguity and worker replacement without retry."""
import pytest
from app.core.exceptions import AppError

pytestmark=pytest.mark.asyncio


async def ledger_fixture(db, client):
    from tests.test_browser_sessions import register
    from app.database.models.live import LiveAccount, LiveRun
    from app.database.models.strategy import StrategyVersion, Strategy
    from tests.test_strategies_api import _valid_graph
    response=await register(client)
    uid=response.json()['user']['id']
    strategy=Strategy(user_id=uid,name='Ledger test')
    db.add(strategy); await db.flush()
    version=StrategyVersion(strategy_id=strategy.id,version_number=1,graph_json=_valid_graph())
    db.add(version)
    account=LiveAccount(user_id=uid,account_identity='a'*64,fence_token='worker-a')
    db.add(account); await db.flush()
    run=LiveRun(account_id=account.id,user_id=uid,strategy_version_id=version.id,
        symbol='BTCUSDT',timeframe='1h',status='running',policy={'max_notional':'100','max_drawdown':'10'})
    db.add(run); await db.commit()
    return account,run


class FakeExchange:
    def __init__(self): self.calls=[]; self.ambiguous=False
    async def submit(self, params, conditional=False):
        from app.live.ledger import SubmissionFailure
        self.calls.append(params)
        if self.ambiguous: raise SubmissionFailure(ambiguous=True)
        return {'status':'FILLED','orderId':123,'clientOrderId':params['newClientOrderId'],'executedQty':'0.001','avgPrice':'100'}


async def test_entry_intent_persisted_before_external_write_and_replay_never_resubmits(client,db_session):
    from app.live.ledger import Guard, prepare_intent, send_once
    from app.database.models.live import LiveOrder
    account,run=await ledger_fixture(db_session,client)
    guard=Guard(account.id,'worker-a')
    params={'symbol':'BTCUSDT','side':'BUY','type':'MARKET','quantity':'0.001','positionSide':'BOTH'}
    row=await prepare_intent(db_session,guard,run.id,'ENTRY','bar-1',params)
    class InspectExchange(FakeExchange):
        async def submit(self,params,conditional=False):
            saved=await db_session.get(LiveOrder,row.id,populate_existing=True)
            assert saved.state=='SENDING' and saved.client_id==params['newClientOrderId']
            return await super().submit(params,conditional)
    exchange=InspectExchange()
    row=await send_once(db_session,guard,row.id,exchange,entries_allowed=True)
    assert row.state=='FILLED'
    await send_once(db_session,guard,row.id,exchange,entries_allowed=True)
    assert len(exchange.calls)==1
    replay=await prepare_intent(db_session,guard,run.id,'ENTRY','bar-1',params)
    assert replay.id==row.id


async def test_unknown_outcome_stays_unknown_and_is_never_retried(client,db_session):
    from app.live.ledger import Guard, prepare_intent, send_once
    account,run=await ledger_fixture(db_session,client)
    guard=Guard(account.id,'worker-a')
    row=await prepare_intent(db_session,guard,run.id,'ENTRY','bar-1',
        {'symbol':'BTCUSDT','side':'BUY','type':'MARKET','quantity':'0.001','positionSide':'BOTH'})
    exchange=FakeExchange(); exchange.ambiguous=True
    with pytest.raises(AppError): await send_once(db_session,guard,row.id,exchange,entries_allowed=True)
    await db_session.refresh(row)
    assert row.state=='UNKNOWN'
    await send_once(db_session,guard,row.id,exchange,entries_allowed=True)
    assert len(exchange.calls)==1
    with pytest.raises(AppError) as exc:
        await prepare_intent(db_session,guard,run.id,'ENTRY','bar-2',
            {'symbol':'BTCUSDT','side':'BUY','type':'MARKET','quantity':'0.001','positionSide':'BOTH'})
    assert exc.value.code=='LIVE_RECONCILIATION_REQUIRED'


async def test_stale_worker_cannot_submit_or_create_another_intent(client,db_session):
    from app.live.ledger import Guard, prepare_intent, send_once
    account,run=await ledger_fixture(db_session,client)
    guard=Guard(account.id,'worker-a')
    row=await prepare_intent(db_session,guard,run.id,'ENTRY','bar-1',
        {'symbol':'BTCUSDT','side':'BUY','type':'MARKET','quantity':'0.001','positionSide':'BOTH'})
    account.fence_token='worker-b'; await db_session.commit()
    exchange=FakeExchange()
    with pytest.raises(AppError): await send_once(db_session,guard,row.id,exchange,entries_allowed=True)
    with pytest.raises(AppError): await prepare_intent(db_session,guard,run.id,'CLOSE','bar-2',
        {'symbol':'BTCUSDT','side':'SELL','type':'MARKET','quantity':'0.001','positionSide':'BOTH','reduceOnly':'true'})
    assert exchange.calls==[]


async def test_disabled_entries_and_invalid_order_parameters_never_reach_exchange(client,db_session):
    from app.live.ledger import Guard, prepare_intent, send_once
    account,run=await ledger_fixture(db_session,client)
    guard=Guard(account.id,'worker-a')
    params={'symbol':'BTCUSDT','side':'BUY','type':'MARKET','quantity':'0.001','positionSide':'BOTH'}
    row=await prepare_intent(db_session,guard,run.id,'ENTRY','bar-1',params)
    exchange=FakeExchange()
    with pytest.raises(AppError): await send_once(db_session,guard,row.id,exchange,entries_allowed=False)
    assert exchange.calls==[]
    for bad in [{**params,'symbol':'ETHUSDT'}, {**params,'quantity':'NaN'}, {**params,'url':'https://attacker.invalid'},
        {**params,'reduceOnly':'false'}]:
        with pytest.raises(AppError): await prepare_intent(db_session,guard,run.id,'ENTRY','bad-'+str(bad),bad)


async def test_malformed_success_is_unknown_not_a_filled_position(client,db_session):
    from app.live.ledger import Guard, prepare_intent, send_once
    account,run=await ledger_fixture(db_session,client)
    guard=Guard(account.id,'worker-a')
    row=await prepare_intent(db_session,guard,run.id,'ENTRY','bar-1',
        {'symbol':'BTCUSDT','side':'BUY','type':'MARKET','quantity':'0.001','positionSide':'BOTH'})
    class Malformed(FakeExchange):
        async def submit(self,params,conditional=False): return {'status':'FILLED','executedQty':'NaN'}
    result=await send_once(db_session,guard,row.id,Malformed(),entries_allowed=True)
    assert result.state=='UNKNOWN'


async def test_recovery_intent_from_old_cycle_cannot_close_a_new_cycle(client,db_session):
    from app.live.ledger import Guard,prepare_intent,send_once
    account,run=await ledger_fixture(db_session,client)
    guard=Guard(account.id,'worker-a')
    entry=await prepare_intent(db_session,guard,run.id,'ENTRY','bar-1',
        {'symbol':'BTCUSDT','side':'BUY','type':'MARKET','quantity':'0.001','positionSide':'BOTH'})
    await send_once(db_session,guard,entry.id,FakeExchange(),entries_allowed=True)
    close=await prepare_intent(db_session,guard,run.id,'CLOSE','close-1',
        {'symbol':'BTCUSDT','side':'SELL','type':'MARKET','quantity':'0.001','positionSide':'BOTH','reduceOnly':'true'})
    # Simulate an independently reconciled, completed cycle. An old worker must
    # not send its READY recovery intent against the next position.
    run.active_entry_id='another-cycle'
    await db_session.commit()
    exchange=FakeExchange()
    with pytest.raises(AppError) as exc: await send_once(db_session,guard,close.id,exchange)
    assert exc.value.code=='LIVE_CYCLE_CHANGED'
    assert exchange.calls==[]


async def test_completed_protection_cannot_masquerade_as_next_cycle_protection(client,db_session):
    from app.live.ledger import Guard,prepare_intent,send_once
    from app.database.models.live import LiveOrder
    account,run=await ledger_fixture(db_session,client)
    guard=Guard(account.id,'worker-a')
    first=await prepare_intent(db_session,guard,run.id,'ENTRY','bar-1',
        {'symbol':'BTCUSDT','side':'BUY','type':'MARKET','quantity':'0.001','positionSide':'BOTH'})
    await send_once(db_session,guard,first.id,FakeExchange(),entries_allowed=True)
    params={'algoType':'CONDITIONAL','symbol':'BTCUSDT','side':'SELL','type':'STOP_MARKET',
        'positionSide':'BOTH','triggerPrice':'95','closePosition':'true','workingType':'MARK_PRICE'}
    old_stop=await prepare_intent(db_session,guard,run.id,'STOP','stop',params)
    old_stop.state='CANCELED'
    run.active_entry_id=None
    await db_session.commit()
    second=await prepare_intent(db_session,guard,run.id,'ENTRY','bar-2',
        {'symbol':'BTCUSDT','side':'BUY','type':'MARKET','quantity':'0.001','positionSide':'BOTH'})
    await send_once(db_session,guard,second.id,FakeExchange(),entries_allowed=True)
    new_stop=await prepare_intent(db_session,guard,run.id,'STOP','stop',params)
    assert old_stop.id!=new_stop.id and old_stop.client_id!=new_stop.client_id
    assert new_stop.state=='READY' and new_stop.cycle_entry_id==second.id
    with pytest.raises(AppError): await send_once(db_session,guard,old_stop.id,FakeExchange())


async def test_triggered_protection_cannot_regress_to_open(client,db_session):
    from app.live.ledger import Guard,prepare_intent,send_once,observe
    account,run=await ledger_fixture(db_session,client)
    guard=Guard(account.id,'worker-a')
    entry=await prepare_intent(db_session,guard,run.id,'ENTRY','bar-1',
        {'symbol':'BTCUSDT','side':'BUY','type':'MARKET','quantity':'0.001','positionSide':'BOTH'})
    await send_once(db_session,guard,entry.id,FakeExchange(),entries_allowed=True)
    stop=await prepare_intent(db_session,guard,run.id,'STOP','stop',{
        'algoType':'CONDITIONAL','symbol':'BTCUSDT','side':'SELL','type':'STOP_MARKET',
        'positionSide':'BOTH','triggerPrice':'95','closePosition':'true','workingType':'MARK_PRICE'})
    result={'algoId':456,'clientAlgoId':stop.client_id,'algoStatus':'FINISHED','actualOrderId':'789'}
    await observe(db_session,stop.id,result)
    await observe(db_session,stop.id,{})
    assert stop.state=='TRIGGERED' and stop.result['actualOrderId']=='789'
    await observe(db_session,stop.id,{key:value for key,value in result.items() if key!='actualOrderId'})
    assert stop.result['actualOrderId']=='789'
    await observe(db_session,stop.id,{**result,'algoStatus':'NEW'})
    assert stop.state=='TRIGGERED' and stop.result['actualOrderId']=='789'


async def test_idempotent_paths_finish_their_database_transaction(client,db_session):
    from app.live.ledger import Guard,prepare_intent,send_once
    account,run=await ledger_fixture(db_session,client)
    guard=Guard(account.id,'worker-a')
    params={'symbol':'BTCUSDT','side':'BUY','type':'MARKET','quantity':'0.001','positionSide':'BOTH'}
    entry=await prepare_intent(db_session,guard,run.id,'ENTRY','bar-1',params)
    await prepare_intent(db_session,guard,run.id,'ENTRY','bar-1',params)
    assert not db_session.in_transaction()
    exchange=FakeExchange()
    await send_once(db_session,guard,entry.id,exchange,entries_allowed=True)
    await send_once(db_session,guard,entry.id,exchange,entries_allowed=True)
    assert not db_session.in_transaction() and len(exchange.calls)==1


async def test_exchange_order_identity_survives_unknown_observations(client,db_session):
    from app.live.ledger import Guard,prepare_intent,observe
    account,run=await ledger_fixture(db_session,client)
    entry=await prepare_intent(db_session,Guard(account.id,'worker-a'),run.id,'ENTRY','bar-1',
        {'symbol':'BTCUSDT','side':'BUY','type':'MARKET','quantity':'0.001','positionSide':'BOTH'})
    initial={'orderId':123,'clientOrderId':entry.client_id,'status':'NEW','executedQty':'0'}
    await observe(db_session,entry.id,initial)
    await observe(db_session,entry.id,{})
    replacement={**initial,'orderId':456,'status':'FILLED','executedQty':'0.001'}
    await observe(db_session,entry.id,replacement)
    await observe(db_session,entry.id,replacement)
    assert entry.state=='UNKNOWN' and entry.filled_quantity==0 and entry.result['orderId']==123
    await observe(db_session,entry.id,{**initial,'status':'FILLED','executedQty':'0.001'})
    assert entry.state=='FILLED' and entry.result['orderId']==123


async def test_disconnect_cannot_remove_credentials_for_an_unfinished_run(client,db_session):
    from app.database.models.exchange_connection import ExchangeConnection
    from app.database.models.account_security import AccountSecurity
    from app.database.models.browser_session import BrowserSession
    from app.database.models.strategy import StrategyVersion
    from app.auth.sessions import digest
    from app.core.security import encrypt_secret
    from datetime import datetime,timezone
    from tests.test_account_security import csrf_headers
    account,run=await ledger_fixture(db_session,client)
    connection=ExchangeConnection(user_id=account.user_id,exchange_name='binanceusdm',is_testnet=False,
        is_active=True,api_key_encrypted=encrypt_secret('fake'),api_secret_encrypted=encrypt_secret('fake'))
    db_session.add(connection)
    db_session.add(AccountSecurity(user_id=account.user_id,email_verified_at=datetime.now(timezone.utc),
        mfa_secret_encrypted=encrypt_secret('JBSWY3DPEHPK3PXP')))
    session=await db_session.get(BrowserSession,digest(client.cookies.get('algoflow_session')))
    session.mfa_at=datetime.now(timezone.utc)
    await db_session.flush()
    account.connection_id=connection.id
    await db_session.commit()
    response=await client.delete('/api/exchanges/'+connection.id,headers=await csrf_headers(client))
    assert response.status_code==409 and response.json()['error']['code']=='LIVE_RUN_ACTIVE'
    await db_session.refresh(connection)
    assert connection.is_active
    # Even a stopped run keeps its strategy version and connection audit trail.
    run.status='stopped'
    await db_session.commit()
    version=await db_session.get(StrategyVersion,run.strategy_version_id)
    response=await client.delete('/api/strategies/'+version.strategy_id,
        headers=await csrf_headers(client))
    assert response.status_code==409 and response.json()['error']['code']=='STRATEGY_IN_USE'
    response=await client.delete('/api/exchanges/'+connection.id,headers=await csrf_headers(client))
    assert response.status_code==204
    await db_session.refresh(connection)
    assert not connection.is_active


async def test_conditional_response_cannot_claim_a_position_fill(client,db_session):
    from app.live.ledger import Guard,prepare_intent,send_once,observe
    account,run=await ledger_fixture(db_session,client)
    guard=Guard(account.id,'worker-a')
    entry=await prepare_intent(db_session,guard,run.id,'ENTRY','bar-1',
        {'symbol':'BTCUSDT','side':'BUY','type':'MARKET','quantity':'0.001','positionSide':'BOTH'})
    await send_once(db_session,guard,entry.id,FakeExchange(),entries_allowed=True)
    stop=await prepare_intent(db_session,guard,run.id,'STOP','stop',{
        'algoType':'CONDITIONAL','symbol':'BTCUSDT','side':'SELL','type':'STOP_MARKET',
        'positionSide':'BOTH','triggerPrice':'95','closePosition':'true','workingType':'MARK_PRICE'})
    await observe(db_session,stop.id,{'algoId':456,'clientAlgoId':stop.client_id,'algoStatus':'FILLED'})
    assert stop.state=='UNKNOWN' and stop.filled_quantity==0
