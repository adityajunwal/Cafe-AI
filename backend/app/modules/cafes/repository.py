from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.modules.auth_tenancy.repository import TenantRepository
from app.modules.auth_tenancy.security import create_qr_token


class CafeRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.cafes

    async def get_by_id(self, cafe_id: str) -> Optional[Dict[str, Any]]:
        try:
            query = {"_id": ObjectId(cafe_id) if ObjectId.is_valid(cafe_id) else cafe_id}
        except Exception:
            query = {"_id": cafe_id}
        return await self.collection.find_one(query)

    async def get_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one({"slug": slug})

    async def create(self, cafe_doc: Dict[str, Any]) -> str:
        doc = dict(cafe_doc)
        doc["cache_version"] = 1
        doc["created_at"] = datetime.now(timezone.utc)
        doc["updated_at"] = doc["created_at"]
        result = await self.collection.insert_one(doc)
        return str(result.inserted_id)

    async def update(self, cafe_id: str, updates: Dict[str, Any]) -> bool:
        try:
            query = {"_id": ObjectId(cafe_id) if ObjectId.is_valid(cafe_id) else cafe_id}
        except Exception:
            query = {"_id": cafe_id}

        upd = dict(updates)
        upd["updated_at"] = datetime.now(timezone.utc)
        result = await self.collection.update_one(
            query,
            {"$set": upd, "$inc": {"cache_version": 1}}
        )
        return result.modified_count > 0

    async def bump_cache_version(self, cafe_id: str) -> int:
        try:
            query = {"_id": ObjectId(cafe_id) if ObjectId.is_valid(cafe_id) else cafe_id}
        except Exception:
            query = {"_id": cafe_id}
        result = await self.collection.find_one_and_update(
            query,
            {"$inc": {"cache_version": 1}, "$set": {"updated_at": datetime.now(timezone.utc)}},
            return_document=True,
        )
        return result.get("cache_version", 1) if result else 1


class TableRepository(TenantRepository):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "tables")

    async def create_table(self, cafe_id: str, table_data: Dict[str, Any]) -> str:
        table_number = str(table_data["number"])
        # Temporary ID placeholder to sign QR token
        temp_id = str(ObjectId())
        qr_token = create_qr_token(cafe_id=cafe_id, table_id=temp_id, table_number=table_number)

        doc = dict(table_data)
        doc["_id"] = ObjectId(temp_id)
        doc["cafe_id"] = cafe_id
        doc["qr_token"] = qr_token
        doc["created_at"] = datetime.now(timezone.utc)

        result = await self.collection.insert_one(doc)
        return str(result.inserted_id)

    async def get_by_number(self, cafe_id: str, number: str) -> Optional[Dict[str, Any]]:
        return await self.find_one(cafe_id, {"number": str(number)})

    async def get_by_qr_token(self, cafe_id: str, qr_token: str) -> Optional[Dict[str, Any]]:
        return await self.find_one(cafe_id, {"qr_token": qr_token})
