from datetime import datetime, timezone
from typing import Any, Dict, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from app.modules.auth_tenancy.repository import TenantRepository
from app.modules.bills.models import BillResponse, BillTaxBreakdown
from app.modules.cafes.repository import CafeRepository
from app.modules.orders.repository import OrderRepository


class BillService(TenantRepository):
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        order_repo: OrderRepository,
        cafe_repo: CafeRepository,
    ):
        super().__init__(db, "bills")
        self.order_repo = order_repo
        self.cafe_repo = cafe_repo

    async def _get_next_bill_number(self, cafe_id: str) -> str:
        """Atomically increments sequential bill counter per cafe."""
        now = datetime.now(timezone.utc)
        # Financial year string (e.g. FY26)
        year_str = f"FY{now.strftime('%y')}"
        counter_key = f"bill_{year_str}"

        counter_doc = await self.db.counters.find_one_and_update(
            {"cafe_id": cafe_id, "key": counter_key},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        seq_num = counter_doc.get("seq", 1)
        return f"{year_str}-{seq_num:05d}"

    async def get_or_generate_bill(self, cafe_id: str, order_id: str) -> Dict[str, Any]:
        # Check if bill already exists
        existing = await self.find_one(cafe_id, {"order_id": order_id})
        if existing:
            return existing

        order = await self.order_repo.get_by_id(cafe_id, order_id)
        if not order:
            raise ValueError("Order not found")

        cafe = await self.cafe_repo.get_by_id(cafe_id)
        if not cafe:
            raise ValueError("Cafe not found")

        bill_number = await self._get_next_bill_number(cafe_id)
        tax_config = cafe.get("tax_config", {})

        taxable_amount = max(0, order["subtotal_paise"] - order.get("discount_paise", 0))

        # Tax calculations
        cgst_paise = 0
        sgst_paise = 0
        if tax_config.get("gst_enabled"):
            total_gst_percent = tax_config.get("gst_rate_percent", 5.0)
            half_percent = total_gst_percent / 2.0
            cgst_paise = int((taxable_amount * half_percent) / 100)
            sgst_paise = int((taxable_amount * half_percent) / 100)

        sc_paise = 0
        if tax_config.get("service_charge_percent", 0.0) > 0:
            sc_rate = tax_config.get("service_charge_percent", 0.0)
            sc_paise = int((taxable_amount * sc_rate) / 100)

        total_tax_paise = cgst_paise + sgst_paise + sc_paise
        final_total = taxable_amount + total_tax_paise

        now = datetime.now(timezone.utc)
        bill_doc: Dict[str, Any] = {
            "cafe_id": cafe_id,
            "cafe_name": cafe.get("name", "Cafe"),
            "bill_number": bill_number,
            "order_id": order_id,
            "table_number": order.get("table_number", "1"),
            "items": order.get("items", []),
            "subtotal_paise": order["subtotal_paise"],
            "discount_paise": order.get("discount_paise", 0),
            "tax_breakdown": {
                "taxable_amount_paise": taxable_amount,
                "cgst_percent": 2.5,
                "cgst_paise": cgst_paise,
                "sgst_percent": 2.5,
                "sgst_paise": sgst_paise,
                "service_charge_percent": tax_config.get("service_charge_percent", 0.0),
                "service_charge_paise": sc_paise,
                "total_tax_paise": total_tax_paise,
            },
            "total_paise": final_total,
            "gstin": tax_config.get("gstin"),
            "created_at": now,
        }

        bill_id = await self.insert_one(cafe_id, bill_doc)
        bill_doc["_id"] = bill_id
        return bill_doc
