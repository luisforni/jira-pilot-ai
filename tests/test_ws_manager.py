from unittest.mock import AsyncMock, MagicMock

import pytest

from api.ws.manager import ConnectionManager


@pytest.mark.asyncio
async def test_connect_and_disconnect():
    mgr = ConnectionManager()
    ws = MagicMock()
    ws.accept = AsyncMock()

    await mgr.connect(ws, room="room-1")
    assert mgr.total_connections() == 1

    mgr.disconnect(ws, room="room-1")
    assert mgr.total_connections() == 0


@pytest.mark.asyncio
async def test_broadcast_to_room():
    mgr = ConnectionManager()

    ws1 = MagicMock()
    ws1.accept = AsyncMock()
    ws1.send_json = AsyncMock()

    ws2 = MagicMock()
    ws2.accept = AsyncMock()
    ws2.send_json = AsyncMock()

    await mgr.connect(ws1, room="task-abc")
    await mgr.connect(ws2, room="task-xyz")

    await mgr.broadcast({"type": "test"}, room="task-abc")

    ws1.send_json.assert_called_once_with({"type": "test"})
    ws2.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_global_room_receives_all():
    mgr = ConnectionManager()

    ws_global = MagicMock()
    ws_global.accept = AsyncMock()
    ws_global.send_json = AsyncMock()

    ws_specific = MagicMock()
    ws_specific.accept = AsyncMock()
    ws_specific.send_json = AsyncMock()

    await mgr.connect(ws_global, room="")
    await mgr.connect(ws_specific, room="task-abc")

    await mgr.broadcast({"type": "update"}, room="task-abc")

    # global room always receives, plus the specific room
    ws_global.send_json.assert_called_once()
    ws_specific.send_json.assert_called_once()
