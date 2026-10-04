from datetime import datetime, timezone
from typing import Any, Dict, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.modules.auth_tenancy.repository import TenantRepository


class CartRepository(TenantRepository):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "carts")

    async def get_cart(self, cafe_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        return await self.find_one(cafe_id, {"session_id": session_id})

    async def save_cart(self, cafe_id: str, session_id: str, cart_data: Dict[str, Any]) -> None:
        doc = dict(cart_data)
        doc["cafe_id"] = cafe_id
        doc["session_id"] = session_id
        doc["updated_at"] = datetime.now(timezone.utc)
        await self.collection.update_one(
            {"cafe_id": cafe_id, "session_id": session_id},
            {"$set": doc},
            upsert=True,
        )

    async def clear_cart(self, cafe_id: str, session_id: str) -> None:
        await self.collection.delete_one({"cafe_id": cafe_id, "session_id": session_id})
