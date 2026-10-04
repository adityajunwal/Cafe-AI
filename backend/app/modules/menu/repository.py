from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.modules.auth_tenancy.repository import TenantRepository


class MenuRepository(TenantRepository):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "menu_items")

    async def get_item(self, cafe_id: str, item_id: str) -> Optional[Dict[str, Any]]:
        return await self.find_by_id(cafe_id, item_id)

    async def get_items_by_ids(self, cafe_id: str, item_ids: List[str]) -> List[Dict[str, Any]]:
        obj_ids = [ObjectId(i) if ObjectId.is_valid(i) else i for i in item_ids]
        return await self.find_all(cafe_id, {"_id": {"$in": obj_ids}})

    async def get_published_menu(self, cafe_id: str) -> List[Dict[str, Any]]:
        return await self.find_all(
            cafe_id,
            {"status": "published"},
            sort=[("category", 1), ("name", 1)],
            limit=500,
        )

    async def create_item(self, cafe_id: str, item_data: Dict[str, Any]) -> str:
        doc = dict(item_data)
        doc["created_at"] = datetime.now(timezone.utc)
        doc["updated_at"] = doc["created_at"]
        return await self.insert_one(cafe_id, doc)

    async def update_item(self, cafe_id: str, item_id: str, updates: Dict[str, Any]) -> bool:
        try:
            oid = ObjectId(item_id) if ObjectId.is_valid(item_id) else item_id
        except Exception:
            oid = item_id

        upd = dict(updates)
        upd["updated_at"] = datetime.now(timezone.utc)
        count = await self.update_one(cafe_id, {"_id": oid}, {"$set": upd})
        return count > 0

    async def set_availability(self, cafe_id: str, item_id: str, is_available: bool) -> bool:
        return await self.update_item(cafe_id, item_id, {"is_available": is_available})


class MenuCategoryRepository(TenantRepository):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "menu_categories")

    async def get_categories(self, cafe_id: str) -> List[Dict[str, Any]]:
        return await self.find_all(cafe_id, {"is_active": True}, sort=[("sort_order", 1)])

    async def create_category(self, cafe_id: str, data: Dict[str, Any]) -> str:
        return await self.insert_one(cafe_id, data)


class DealRepository(TenantRepository):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "deals")

    async def get_active_deals(self, cafe_id: str) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        query = {
            "is_active": True,
            "$or": [{"valid_from": None}, {"valid_from": {"$lte": now}}],
            "$and": [{"$or": [{"valid_until": None}, {"valid_until": {"$gte": now}}]}],
        }
        return await self.find_all(cafe_id, query)

    async def get_by_code(self, cafe_id: str, code: str) -> Optional[Dict[str, Any]]:
        return await self.find_one(cafe_id, {"code": code.upper().strip(), "is_active": True})
