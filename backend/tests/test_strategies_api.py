import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


def _node(node_id: str, node_type: str, params: dict | None = None) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "position": {"x": 0, "y": 0},
        "data": {"label": node_type, "nodeType": node_type, "params": params or {}},
    }


def _valid_graph() -> dict:
    """Matches the real graph shipped in src/store/useStrategyStore.ts."""
    return {
        "nodes": [
            _node("rsi-1", "rsi", {"period": 14, "oversold": 30, "overbought": 70}),
            _node("condition-1", "condition", {"operator": "<", "value": 30}),
            _node("buy-1", "buy", {"amount": 0.1, "type": "market"}),
            _node("stopLoss-1", "stopLoss", {"percent": 2}),
        ],
        "edges": [
            {"id": "e1", "source": "rsi-1", "target": "condition-1"},
            {"id": "e2", "source": "condition-1", "target": "buy-1"},
            {"id": "e3", "source": "condition-1", "target": "stopLoss-1"},
        ],
    }


async def _create_strategy(client: AsyncClient, headers: dict, name: str = "RSI Oversold Strategy") -> dict:
    response = await client.post(
        "/api/strategies",
        json={"name": name, "description": "Buy when RSI < 30", "graph": _valid_graph()},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def test_create_strategy_creates_version_one(client: AsyncClient, auth_headers: dict):
    body = await _create_strategy(client, auth_headers)
    assert body["current_version"] == 1
    assert len(body["versions"]) == 1
    assert body["versions"][0]["version_number"] == 1
    assert body["versions"][0]["graph"]["nodes"][0]["id"] == "rsi-1"


async def test_list_strategies_returns_created_strategy(client: AsyncClient, auth_headers: dict):
    created = await _create_strategy(client, auth_headers)
    response = await client.get("/api/strategies", headers=auth_headers)
    assert response.status_code == 200
    ids = [s["id"] for s in response.json()]
    assert created["id"] in ids


async def test_get_strategy_returns_full_detail(client: AsyncClient, auth_headers: dict):
    created = await _create_strategy(client, auth_headers)
    response = await client.get(f"/api/strategies/{created['id']}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_update_strategy_creates_new_version_without_destroying_old(client: AsyncClient, auth_headers: dict):
    created = await _create_strategy(client, auth_headers)

    new_graph = _valid_graph()
    new_graph["nodes"][1]["data"]["params"]["value"] = 25  # tweak RSI threshold

    response = await client.put(
        f"/api/strategies/{created['id']}",
        json={"graph": new_graph},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["current_version"] == 2
    assert len(body["versions"]) == 2
    assert body["versions"][0]["version_number"] == 1
    assert body["versions"][1]["version_number"] == 2
    # the original version's graph is untouched
    assert body["versions"][0]["graph"]["nodes"][1]["data"]["params"]["value"] == 30
    assert body["versions"][1]["graph"]["nodes"][1]["data"]["params"]["value"] == 25


async def test_validate_saved_strategy_is_valid(client: AsyncClient, auth_headers: dict):
    created = await _create_strategy(client, auth_headers)
    response = await client.post(f"/api/strategies/{created['id']}/validate", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["valid"] is True


async def test_validate_does_not_persist_a_new_version(client: AsyncClient, auth_headers: dict):
    created = await _create_strategy(client, auth_headers)

    broken_graph = {"nodes": [_node("buy-1", "buy", {"amount": 0.1})], "edges": []}
    response = await client.post(
        f"/api/strategies/{created['id']}/validate",
        json={"graph": broken_graph},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["valid"] is False

    fetched = await client.get(f"/api/strategies/{created['id']}", headers=auth_headers)
    assert fetched.json()["current_version"] == 1  # unchanged


async def test_delete_strategy(client: AsyncClient, auth_headers: dict):
    created = await _create_strategy(client, auth_headers)
    delete_response = await client.delete(f"/api/strategies/{created['id']}", headers=auth_headers)
    assert delete_response.status_code == 204

    get_response = await client.get(f"/api/strategies/{created['id']}", headers=auth_headers)
    assert get_response.status_code == 404


async def test_user_cannot_access_another_users_strategy(client: AsyncClient, auth_headers: dict):
    created = await _create_strategy(client, auth_headers)

    other_register = await client.post(
        "/api/auth/register", json={"email": "other-user@example.com", "password": "password123"}
    )
    other_headers = {"Authorization": f"Bearer {other_register.json()['access_token']}"}

    get_response = await client.get(f"/api/strategies/{created['id']}", headers=other_headers)
    assert get_response.status_code == 404

    put_response = await client.put(
        f"/api/strategies/{created['id']}", json={"graph": _valid_graph()}, headers=other_headers
    )
    assert put_response.status_code == 404

    delete_response = await client.delete(f"/api/strategies/{created['id']}", headers=other_headers)
    assert delete_response.status_code == 404

    list_response = await client.get("/api/strategies", headers=other_headers)
    assert created["id"] not in [s["id"] for s in list_response.json()]

    for action in ('validate', 'execute'):
        response = await client.post(f"/api/strategies/{created['id']}/{action}", headers=other_headers)
        assert response.status_code == 404
    own = await client.get(f"/api/strategies/{created['id']}", headers=auth_headers)
    assert own.status_code == 200
    assert own.json()['current_version'] == 1
