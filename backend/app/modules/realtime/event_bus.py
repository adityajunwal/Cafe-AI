import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from app.logging import logger


class DomainEvent:
    def __init__(self, cafe_id: str, event_type: str, data: Dict[str, Any], seq: int = 0):
        self.cafe_id = cafe_id
        self.event_type = event_type
        self.data = data
        self.seq = seq
        self.created_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.event_type,
            "seq": self.seq,
            "cafe_id": self.cafe_id,
            "data": self.data,
            "created_at": self.created_at.isoformat(),
        }


class EventBus:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self._subscribers: List[Callable[[DomainEvent], Any]] = []

    def subscribe(self, callback: Callable[[DomainEvent], Any]) -> None:
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[DomainEvent], Any]) -> None:
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    async def _get_next_seq(self, cafe_id: str) -> int:
        counter = await self.db.counters.find_one_and_update(
            {"cafe_id": cafe_id, "key": "event_seq"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return counter.get("seq", 1)

    async def publish(self, cafe_id: str, event_type: str, data: Dict[str, Any]) -> DomainEvent:
        seq = await self._get_next_seq(cafe_id)
        event = DomainEvent(cafe_id=cafe_id, event_type=event_type, data=data, seq=seq)

        # 1. Authoritative persistence in event store for resume & replay
        event_doc = {
            "cafe_id": cafe_id,
            "seq": seq,
            "event_type": event_type,
            "data": data,
            "created_at": event.created_at,
        }
        try:
            await self.db.events.insert_one(event_doc)
        except Exception as e:
            logger.error(f"Failed to persist event to store: {e}")

        # 2. Local in-process fanout to active WebSocket connections
        for callback in list(self._subscribers):
            try:
                res = callback(event)
                if asyncio.iscoroutine(res):
                    asyncio.create_task(res)
            except Exception as e:
                logger.warning(f"Error in event subscriber: {e}")

        return event

    async def get_events_after(self, cafe_id: str, after_seq: int, limit: int = 50) -> List[Dict[str, Any]]:
        cursor = self.db.events.find(
            {"cafe_id": cafe_id, "seq": {"$gt": after_seq}}
        ).sort("seq", 1).limit(limit)
        events = await cursor.to_list(length=limit)
        return [
            {
                "type": e["event_type"],
                "seq": e["seq"],
                "replay": True,
                "data": e["data"],
            }
            for e in events
        ]
