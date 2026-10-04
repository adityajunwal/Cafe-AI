import json
from typing import Any, Dict, List, Optional, Set
from fastapi import WebSocket
from app.modules.auth_tenancy.security import decode_ws_ticket
from app.modules.realtime.event_bus import DomainEvent, EventBus
from app.logging import logger


class WSClientConnection:
    def __init__(
        self,
        websocket: WebSocket,
        cafe_id: str,
        role: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        self.websocket = websocket
        self.cafe_id = cafe_id
        self.role = role
        self.session_id = session_id
        self.user_id = user_id
        self.known_order_ids: Set[str] = set()

    async def send_json(self, data: Dict[str, Any]) -> None:
        try:
            await self.websocket.send_text(json.dumps(data))
        except Exception as e:
            logger.debug(f"Failed to send WS message to client: {e}")


class WebSocketHub:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.connections: List[WSClientConnection] = []
        # Subscribe hub to event bus
        self.event_bus.subscribe(self.handle_domain_event)

    async def authenticate_and_connect(self, websocket: WebSocket, ticket: str) -> Optional[WSClientConnection]:
        try:
            payload = decode_ws_ticket(ticket)
        except Exception as e:
            logger.warning(f"WebSocket ticket rejection: {e}")
            await websocket.close(code=4001, reason="Invalid or expired ticket")
            return None

        cafe_id = payload.get("cafe_id")
        role = payload.get("role")
        session_id = payload.get("session_id")
        user_id = payload.get("user_id")

        if not cafe_id or not role:
            await websocket.close(code=4002, reason="Missing ticket scope")
            return None

        await websocket.accept()
        conn = WSClientConnection(
            websocket=websocket,
            cafe_id=cafe_id,
            role=role,
            session_id=session_id,
            user_id=user_id,
        )
        self.connections.append(conn)
        logger.info(f"WS client connected: cafe={cafe_id}, role={role}, session={session_id}")
        return conn

    def disconnect(self, conn: WSClientConnection) -> None:
        if conn in self.connections:
            self.connections.remove(conn)
            logger.info(f"WS client disconnected: cafe={conn.cafe_id}, role={conn.role}")

    async def handle_client_message(self, conn: WSClientConnection, message: str) -> None:
        try:
            msg_data = json.loads(message)
            msg_type = msg_data.get("type")

            if msg_type == "resume":
                last_seq = msg_data.get("last_seq", 0)
                replays = await self.event_bus.get_events_after(conn.cafe_id, after_seq=last_seq, limit=100)
                for event in replays:
                    if self._should_deliver_event(conn, event["type"], event["data"]):
                        await conn.send_json(event)

            elif msg_type == "ping":
                await conn.send_json({"type": "pong"})

        except Exception as e:
            logger.warning(f"Error handling WS client message: {e}")

    async def handle_domain_event(self, event: DomainEvent) -> None:
        event_dict = {
            "type": event.event_type,
            "seq": event.seq,
            "replay": False,
            "data": event.data,
        }

        # Deliver to matched connections
        for conn in list(self.connections):
            if conn.cafe_id != event.cafe_id:
                continue

            if self._should_deliver_event(conn, event.event_type, event.data):
                await conn.send_json(event_dict)

    def _should_deliver_event(self, conn: WSClientConnection, event_type: str, data: Dict[str, Any]) -> bool:
        # Staff and owners receive all cafe events
        if conn.role in ("staff", "owner", "platform_admin"):
            return True

        # Customer: only receive events for their own session or orders
        if conn.role == "customer":
            event_session = data.get("session_id")
            if event_session and event_session == conn.session_id:
                return True
            order_id = data.get("order_id")
            if order_id and order_id in conn.known_order_ids:
                return True
            return False

        return False
