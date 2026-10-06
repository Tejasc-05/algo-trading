from datetime import datetime, timezone
from types import SimpleNamespace
import threading

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select

from app.core.exceptions import AppError
from app.database.models.paper_trading import PaperAccount, Trade
from app.exchanges.ccxt_service import CCXTExchange
from app.market_data.historical import fetch_latest_ohlcv as real_latest, normalize_ohlcv
from app.schemas.strategy import StrategyGraph, ReactFlowEdge
from app.strategy_engine.conditions import compare
from app.strategy_engine.executor import StrategyExecutor
from app.strategy_engine.validator import validate_strategy_graph
from tests.test_api_endpoints import _create_test_strategy
from tests.test_strategy_engine.test_executor import _node, _edge, make_dummy_candles


def graph_with(source="price", condition=None, extra_nodes=(), extra_edges=()):
    return StrategyGraph.model_validate(dict(nodes=[_node("p", source),
        _node("c", "condition", condition or {"operator": "<", "value": 200}),
        _node("a", "buy", {"amount": 1})] + list(extra_nodes),
        edges=[_edge("e1", "p", "c"), _edge("e2", "c", "a")] + list(extra_edges)))


def test_numeric_source_cannot_gate_action():
    graph = StrategyGraph.model_validate(dict(nodes=[_node("p", "price"), _node("a", "buy", {"amount": 1})],
        edges=[_edge("e", "p", "a")]))
    assert any(e.code == "INVALID_CONNECTION" for e in validate_strategy_graph(graph).errors)
    with pytest.raises(AppError, match="boolean"):
        StrategyExecutor(graph)


def test_nan_inequality_is_unknown():
    out = compare("!=", np.array([np.nan, 10]), 20)
    assert pd.isna(out.iloc[0])
    assert bool(out.iloc[1])


def test_not_does_not_trade_during_indicator_warmup():
    graph = graph_with("rsi", {"operator": ">", "value": 50}, [_node("n", "not")])
    graph.edges = [ReactFlowEdge.model_validate(e) for e in [_edge("e1", "p", "c"), _edge("e2", "c", "n"), _edge("e3", "n", "a")]]
    assert StrategyExecutor(graph).evaluate({"candles": make_dummy_candles(5)}) == []


def test_handles_survive_graph_roundtrip():
    graph = graph_with()
    graph.edges[0].source_handle = "source"
    graph.edges[0].target_handle = "target"
    wire = graph.model_dump(by_alias=True)
    assert wire["edges"][0]["sourceHandle"] == "source"
    assert StrategyGraph.model_validate(wire).edges[0].target_handle == "target"


def test_normalization_deduplicates_and_rejects_infinite_prices():
    rows = [[1700000000000, 10, 11, 9, 10, 1]] * 2
    assert len(normalize_ohlcv(rows)) == 1
    rows[1] = [1700000000001, 10, 11, 9, float("inf"), 1]
    with pytest.raises(ValueError):
        normalize_ohlcv(rows)


@pytest.mark.asyncio
async def test_outage_never_returns_synthetic_market_data(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("offline")
    monkeypatch.setattr("app.market_data.historical._public_exchange", fail)
    with pytest.raises(AppError) as exc:
        await real_latest("BTC/USDT", "1h")
    assert exc.value.code == "MARKET_DATA_UNAVAILABLE"


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled,code", [(False, "LIVE_TRADING_DISABLED"), (True, "LIVE_EXECUTION_NOT_IMPLEMENTED")])
async def test_live_order_can_never_reach_ccxt(monkeypatch, enabled, code):
    monkeypatch.setattr("app.exchanges.ccxt_service.get_settings", lambda: SimpleNamespace(enable_live_trading=enabled))
    exchange = object.__new__(CCXTExchange)
    exchange._exchange = SimpleNamespace(create_order=lambda **kwargs: pytest.fail("Real order attempted"))
    with pytest.raises(AppError) as exc:
        await exchange.create_order("BTC/USDT", "buy", "market", 1)
    assert exc.value.code == code


@pytest.mark.asyncio
async def test_ccxt_reads_run_off_event_loop():
    caller = threading.get_ident()
    exchange = object.__new__(CCXTExchange)
    def load():
        assert threading.get_ident() != caller
        return {"BTC/USDT": {}}
    exchange.exchange_id = "fake"
    exchange._exchange = SimpleNamespace(load_markets=load)
    assert (await exchange.fetch_exchange_info())["market_count"] == 1


async def start_account(client, headers, balance=1000):
    strategy_id = await _create_test_strategy(client, headers)
    res = await client.post("/api/paper-trading/start", headers=headers,
        json=dict(strategy_id=strategy_id, symbol="BTC/USDT", starting_balance=balance))
    assert res.status_code == 201
    return res.json()["id"]


async def order(client, headers, account_id, **overrides):
    payload = dict(paper_account_id=account_id, symbol="BTC/USDT", side="buy", order_type="market", quantity=1)
    payload.update(overrides)
    return await client.post("/api/paper-trading/orders", headers=headers, json=payload)


@pytest.mark.asyncio
async def test_start_checks_strategy_ownership(client, auth_headers):
    strategy_id = await _create_test_strategy(client, auth_headers)
    other = await client.post("/api/auth/register", json=dict(email="other@example.com", password="password123"))
    headers = {"Authorization": "Bearer " + other.json()["access_token"]}
    res = await client.post("/api/paper-trading/start", headers=headers, json=dict(strategy_id=strategy_id, symbol="BTC/USDT"))
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_fill_changes_balance_equity_and_is_not_repeatable(client, auth_headers):
    account_id = await start_account(client, auth_headers)
    created = await order(client, auth_headers, account_id)
    payload = dict(order_id=created.json()["order_id"], current_price=100)
    assert (await client.post("/api/paper-trading/simulate-fill", headers=auth_headers, json=payload)).status_code == 200
    portfolio = (await client.get("/api/portfolio", headers=auth_headers)).json()
    assert portfolio["cash_balance"] == pytest.approx(899.85, abs=.01)
    assert portfolio["total_value"] == pytest.approx(999.9, abs=.01)
    assert len(portfolio["positions"]) == 1
    assert (await client.post("/api/paper-trading/simulate-fill", headers=auth_headers, json=payload)).status_code == 409
    assert len((await client.get("/api/paper-trading/trades", headers=auth_headers)).json()) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("side,price", [("buy", 2000), ("sell", 100)])
async def test_no_overdraft_or_naked_spot_sell(client, auth_headers, side, price):
    account_id = await start_account(client, auth_headers)
    created = await order(client, auth_headers, account_id, side=side)
    filled = await client.post("/api/paper-trading/simulate-fill", headers=auth_headers,
        json=dict(order_id=created.json()["order_id"], current_price=price))
    assert filled.status_code == 409
    assert (await client.get("/api/paper-trading/account", headers=auth_headers)).json()["balance"] == 1000
    assert (await client.get("/api/paper-trading/trades", headers=auth_headers)).json() == []


@pytest.mark.asyncio
async def test_limit_waits_for_matching_price(client, auth_headers):
    account_id = await start_account(client, auth_headers)
    created = await order(client, auth_headers, account_id, order_type="limit", price=90)
    payload = dict(order_id=created.json()["order_id"], current_price=100)
    assert (await client.post("/api/paper-trading/simulate-fill", headers=auth_headers, json=payload)).status_code == 409
    payload["current_price"] = 89
    filled = await client.post("/api/paper-trading/simulate-fill", headers=auth_headers, json=payload)
    assert filled.status_code == 200
    assert filled.json()["executed_price"] <= 90


@pytest.mark.asyncio
async def test_invalid_order_and_negative_fill_price(client, auth_headers):
    account_id = await start_account(client, auth_headers)
    assert (await order(client, auth_headers, account_id, side="oops")).status_code == 422
    assert (await order(client, auth_headers, account_id, order_type="limit")).status_code == 422
    assert (await client.post("/api/paper-trading/simulate-fill", headers=auth_headers,
        json=dict(order_id="absent", current_price=-1))).status_code == 422


@pytest.mark.asyncio
async def test_tick_is_idempotent_per_closed_candle(client, auth_headers, db_session, monkeypatch):
    from app.paper_trading.engine import run_paper_trading_tick
    account_id = await start_account(client, auth_headers)
    account = await db_session.get(PaperAccount, account_id)
    candles = make_dummy_candles(50)
    candles.timestamp = pd.to_datetime(candles.timestamp, utc=True)
    async def data(**kwargs):
        return candles
    monkeypatch.setattr("app.paper_trading.engine.fetch_latest_ohlcv", data)
    graph = graph_with()
    first = await run_paper_trading_tick(db_session, account, graph, "BTC/USDT")
    second = await run_paper_trading_tick(db_session, account, graph, "BTC/USDT")
    assert first["order"] is not None
    assert second["message"] == "Candle already processed"
    assert len(list((await db_session.execute(select(Trade))).scalars())) == 1


def test_reference_backtest_fills_next_open_and_counts_both_fees():
    from app.backtesting.simulator import simulate_strategy_on_ohlcv
    df = pd.DataFrame(dict(timestamp=pd.date_range("2026-01-01", periods=3, freq="h", tz="UTC"),
        open=[100, 101, 105], high=[101, 106, 111], low=[99, 100, 104], close=[100, 105, 110], volume=[1, 1, 1]))
    result = simulate_strategy_on_ohlcv(graph_with(), df, symbol="BTC/USDT", timeframe="1h",
        starting_capital=1000, fees_pct=.01, slippage_pct=0)
    assert result["trade_history"][0]["price"] == 101
    assert result["trade_history"][0]["timestamp"] == df.iloc[1].timestamp
    assert result["metrics"]["net_profit"] == pytest.approx(6.89)
    assert result["metrics"]["num_trades"] == 1
