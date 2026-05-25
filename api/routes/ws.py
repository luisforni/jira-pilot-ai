from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.ws.manager import manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def ws_global(websocket: WebSocket) -> None:
    """Global feed — receives all pipeline events."""
    await manager.connect(websocket, room="")
    try:
        while True:
            await websocket.receive_text()  # keep-alive ping
    except WebSocketDisconnect:
        manager.disconnect(websocket, room="")


@router.websocket("/ws/{task_id}")
async def ws_pipeline(websocket: WebSocket, task_id: str) -> None:
    """Per-pipeline feed — receives events for a specific task."""
    await manager.connect(websocket, room=task_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, room=task_id)
