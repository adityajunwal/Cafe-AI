from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from app.database import get_database
from app.modules.realtime.event_bus import EventBus
from app.modules.realtime.ws_hub import WebSocketHub
from app.logging import logger

router = APIRouter(tags=["Realtime Live Updates"])

_hub_instance = None


def get_ws_hub() -> WebSocketHub:
    global _hub_instance
    if _hub_instance is None:
        db = get_database()
        event_bus = EventBus(db)
        _hub_instance = WebSocketHub(event_bus)
    return _hub_instance


@router.websocket("/v1/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    ticket: str = Query(..., description="Single-use signed WebSocket ticket"),
):
    hub = get_ws_hub()
    client = await hub.authenticate_and_connect(websocket, ticket)
    if not client:
        return

    try:
        while True:
            data = await websocket.receive_text()
            await hub.handle_client_message(client, data)
    except WebSocketDisconnect:
        hub.disconnect(client)
    except Exception as e:
        logger.warning(f"WebSocket connection error: {e}")
        hub.disconnect(client)
