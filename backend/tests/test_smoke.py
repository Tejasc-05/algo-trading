"""E2E smoke test using the same in-memory SQLite + fakeredis setup via conftest."""
import pytest

@pytest.mark.asyncio
async def test_e2e_smoke_flow(client, auth_headers):
    """Full smoke test: register → login → create → execute → portfolio."""
    headers = auth_headers

    # 1. CREATE STRATEGY
    from tests.test_api_endpoints import _create_test_strategy
    sid = await _create_test_strategy(client, headers)
    strat = {"name": "SmokeTest", "graph": {"nodes": [], "edges": []}}
    r = await client.post("/api/strategies", json=strat, headers=headers)
    assert r.status_code == 201, f"CREATE STRATEGY failed: {r.text}"

    # 2. EXECUTE STRATEGY
    r = await client.post(f"/api/strategies/{sid}/execute", headers=headers)
    assert r.status_code == 200, f"EXECUTE failed: {r.text}"

    # 3. LIST STRATEGIES
    r = await client.get("/api/strategies", headers=headers)
    assert r.status_code == 200, f"LIST failed: {r.text}"
    assert len(r.json()) >= 1

    # 4. PAPER TRADING SESSIONS
    r = await client.get("/api/paper-trading/trades", headers=headers)
    assert r.status_code == 200, f"PAPER TRADING failed: {r.text}"

    # 5. PORTFOLIO
    r = await client.get("/api/portfolio", headers=headers)
    assert r.status_code == 200, f"PORTFOLIO failed: {r.text}"