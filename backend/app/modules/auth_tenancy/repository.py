from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from bson import ObjectId


class TenantRepository:
    """
    Mandatory base repository class for all tenant-scoped MongoDB access.
    Enforces that 'cafe_id' is non-negotiable on all reads, writes, and updates.
    """

    def __init__(self, db: AsyncIOMotorDatabase, collection_name: str):
        self.db = db
        self.collection_name = collection_name
        self.collection: AsyncIOMotorCollection = db[collection_name]

    def _scope_filter(self, cafe_id: str, query: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not cafe_id or not isinstance(cafe_id, str):
            raise ValueError("cafe_id is required and must be a non-empty string for tenant queries")
        scoped = {"cafe_id": cafe_id}
        if query:
            scoped.update(query)
        return scoped

    async def find_one(self, cafe_id: str, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        scoped_query = self._scope_filter(cafe_id, query)
        return await self.collection.find_one(scoped_query)

    async def find_by_id(self, cafe_id: str, entity_id: str) -> Optional[Dict[str, Any]]:
        try:
            obj_id = ObjectId(entity_id) if ObjectId.is_valid(entity_id) else entity_id
        except Exception:
            obj_id = entity_id
        return await self.find_one(cafe_id, {"_id": obj_id})

    async def find_all(
        self,
        cafe_id: str,
        query: Optional[Dict[str, Any]] = None,
        sort: Optional[List[tuple]] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        scoped_query = self._scope_filter(cafe_id, query)
        cursor = self.collection.find(scoped_query)
        if sort:
            cursor = cursor.sort(sort)
        if skip > 0:
            cursor = cursor.skip(skip)
        if limit > 0:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=limit)

    async def insert_one(self, cafe_id: str, document: Dict[str, Any]) -> str:
        if not cafe_id or not isinstance(cafe_id, str):
            raise ValueError("cafe_id is required and must be a non-empty string for tenant insertion")
        doc_copy = dict(document)
        doc_copy["cafe_id"] = cafe_id
        result = await self.collection.insert_one(doc_copy)
        return str(result.inserted_id)

    async def update_one(
        self,
        cafe_id: str,
        filter_query: Dict[str, Any],
        update_doc: Dict[str, Any],
        upsert: bool = False,
    ) -> int:
        scoped_query = self._scope_filter(cafe_id, filter_query)
        result = await self.collection.update_one(scoped_query, update_doc, upsert=upsert)
        return result.modified_count

    async def find_one_and_update(
        self,
        cafe_id: str,
        filter_query: Dict[str, Any],
        update_doc: Dict[str, Any],
        return_document: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Used for atomic compare-and-set state transitions."""
        from pymongo import ReturnDocument

        scoped_query = self._scope_filter(cafe_id, filter_query)
        ret_doc = ReturnDocument.AFTER if return_document else ReturnDocument.BEFORE
        return await self.collection.find_one_and_update(scoped_query, update_doc, return_document=ret_doc)

    async def delete_one(self, cafe_id: str, filter_query: Dict[str, Any]) -> int:
        scoped_query = self._scope_filter(cafe_id, filter_query)
        result = await self.collection.delete_one(scoped_query)
        return result.deleted_count

    async def count(self, cafe_id: str, query: Optional[Dict[str, Any]] = None) -> int:
        scoped_query = self._scope_filter(cafe_id, query)
        return await self.collection.count_documents(scoped_query)
