from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi import WebSocketDisconnect

from app.websocket.manager import WebSocketManager, websocket_endpoint
from app.redis.pubsub import publish_user_event, subscribe_to_user_channel


@pytest.mark.asyncio
async def test_manager_only_sends_to_target_user():
    manager = WebSocketManager()
    a = SimpleNamespace(accept=AsyncMock(), send_text=AsyncMock(), headers={})
    b = SimpleNamespace(accept=AsyncMock(), send_text=AsyncMock(), headers={})
    await manager.connect("a", a)
    await manager.connect("b", b)
    await manager.broadcast("a", "paper_order", {"order_id": "1"})
    a.send_text.assert_awaited_once()
    b.send_text.assert_not_awaited()
    manager.disconnect("a", a)
    assert "a" not in manager._connections


@pytest.mark.asyncio
async def test_unauthenticated_socket_never_accepts(monkeypatch):
    authenticate = AsyncMock(return_value=None)
    monkeypatch.setattr("app.api.dependencies.get_user_from_websocket", authenticate)
    socket = SimpleNamespace(headers={}, accept=AsyncMock(), close=AsyncMock())
    await websocket_endpoint(socket)
    socket.close.assert_awaited_once_with(code=1008)
    socket.accept.assert_not_awaited()


@pytest.mark.asyncio
async def test_disallowed_socket_origin_never_authenticates(monkeypatch):
    authenticate = AsyncMock()
    monkeypatch.setattr("app.api.dependencies.get_user_from_websocket", authenticate)
    socket = SimpleNamespace(headers={"origin": "https://untrusted.example"}, close=AsyncMock())
    await websocket_endpoint(socket)
    authenticate.assert_not_awaited()
    socket.close.assert_awaited_once_with(code=1008)


@pytest.mark.asyncio
async def test_redis_channels_are_user_scoped(monkeypatch):
    publisher = AsyncMock()
    monkeypatch.setattr("app.redis.pubsub.publish_event", publisher)
    await publish_user_event("owner", "paper_order", {"id": "1"})
    publisher.assert_awaited_once_with("user:owner", {"event": "paper_order", "data": {"id": "1"}})
