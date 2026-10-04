from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from app.modules.auth_tenancy.repository import TenantRepository
from app.modules.orders.models import OrderStatus, PaymentStatus, StatusHistoryEntry


class OrderRepository(TenantRepository):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "orders")

    async def get_by_id(self, cafe_id: str, order_id: str) -> Optional[Dict[str, Any]]:
        return await self.find_by_id(cafe_id, order_id)

    async def get_by_idempotency_key(self, cafe_id: str, key: str) -> Optional[Dict[str, Any]]:
        return await self.find_one(cafe_id, {"idempotency_key": key})

    async def get_active_orders_for_session(self, cafe_id: str, session_id: str) -> List[Dict[str, Any]]:
        return await self.find_all(
            cafe_id,
            {"session_id": session_id},
            sort=[("created_at", -1)],
            limit=20,
        )

    async def get_kanban_orders(self, cafe_id: str) -> List[Dict[str, Any]]:
        """Active orders for the staff Kanban board."""
        active_statuses = [
            OrderStatus.AWAITING_PAYMENT.value,
            OrderStatus.NEW.value,
            OrderStatus.PREPARING.value,
            OrderStatus.READY.value,
        ]
        return await self.find_all(
            cafe_id,
            {"order_status": {"$in": active_statuses}},
            sort=[("created_at", 1)],
            limit=200,
        )

    async def atomic_transition_order(
        self,
        cafe_id: str,
        order_id: str,
        allowed_from_statuses: List[OrderStatus],
        to_status: OrderStatus,
        actor_type: str,
        actor_id: Optional[str] = None,
        actor_name: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Atomic Compare-and-Set: only succeeds if current order_status is in allowed_from_statuses.
        Prevents race conditions between staff clicks and sweeper timeouts.
        """
        try:
            oid = ObjectId(order_id) if ObjectId.is_valid(order_id) else order_id
        except Exception:
            oid = order_id

        history_entry = StatusHistoryEntry(
            status=f"order:{to_status.value}",
            actor_type=actor_type,
            actor_id=actor_id,
            actor_name=actor_name,
            timestamp=datetime.now(timezone.utc),
            notes=notes,
        ).model_dump()

        filter_query = {
            "_id": oid,
            "cafe_id": cafe_id,
            "order_status": {"$in": [s.value for s in allowed_from_statuses]},
        }
        update_doc = {
            "$set": {
                "order_status": to_status.value,
                "updated_at": datetime.now(timezone.utc),
            },
            "$push": {"status_history": history_entry},
        }

        return await self.collection.find_one_and_update(
            filter_query,
            update_doc,
            return_document=ReturnDocument.AFTER,
        )

    async def record_payment_submission(
        self,
        cafe_id: str,
        order_id: str,
        payment_attempt: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        try:
            oid = ObjectId(order_id) if ObjectId.is_valid(order_id) else order_id
        except Exception:
            oid = order_id

        history_entry = StatusHistoryEntry(
            status=f"payment:{PaymentStatus.SUBMITTED.value}",
            actor_type="customer",
            notes="Customer submitted payment evidence",
        ).model_dump()

        filter_query = {
            "_id": oid,
            "cafe_id": cafe_id,
            "payment_status": {"$in": [PaymentStatus.UNPAID.value, PaymentStatus.REJECTED.value]},
        }
        update_doc = {
            "$set": {
                "payment_status": PaymentStatus.SUBMITTED.value,
                "updated_at": datetime.now(timezone.utc),
            },
            "$push": {
                "payments": payment_attempt,
                "status_history": history_entry,
            },
        }

        return await self.collection.find_one_and_update(
            filter_query,
            update_doc,
            return_document=ReturnDocument.AFTER,
        )

    async def verify_payment(
        self,
        cafe_id: str,
        order_id: str,
        is_approved: bool,
        verified_by: str,
        rejection_reason: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Staff verification of manual UPI payment."""
        try:
            oid = ObjectId(order_id) if ObjectId.is_valid(order_id) else order_id
        except Exception:
            oid = order_id

        new_payment_status = PaymentStatus.VERIFIED.value if is_approved else PaymentStatus.REJECTED.value
        new_order_status = OrderStatus.NEW.value if is_approved else OrderStatus.AWAITING_PAYMENT.value

        history_entry = StatusHistoryEntry(
            status=f"payment:{new_payment_status}",
            actor_type="staff",
            actor_id=verified_by,
            notes=f"Staff verification: {'Approved' if is_approved else 'Rejected: ' + (rejection_reason or '')}",
        ).model_dump()

        filter_query = {
            "_id": oid,
            "cafe_id": cafe_id,
            "payment_status": PaymentStatus.SUBMITTED.value,
        }

        set_fields: Dict[str, Any] = {
            "payment_status": new_payment_status,
            "updated_at": datetime.now(timezone.utc),
            "payments.$.verified_by": verified_by,
            "payments.$.verified_at": datetime.now(timezone.utc),
        }
        if is_approved:
            set_fields["order_status"] = new_order_status
        else:
            set_fields["payments.$.rejection_reason"] = rejection_reason

        update_doc = {
            "$set": set_fields,
            "$push": {"status_history": history_entry},
        }

        return await self.collection.find_one_and_update(
            filter_query,
            update_doc,
            return_document=ReturnDocument.AFTER,
        )
