from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from app.modules.cafes.models import PaymentMode
from app.modules.cafes.repository import CafeRepository
from app.modules.cart.models import Cart
from app.modules.cart.repository import CartRepository
from app.modules.menu.repository import MenuRepository
from app.modules.orders.models import (
    OrderItemSnapshot,
    OrderStatus,
    PaymentAttempt,
    PaymentMethod,
    PaymentStatus,
    StatusHistoryEntry,
)
from app.modules.orders.repository import OrderRepository
from app.logging import logger


class OrderService:
    def __init__(
        self,
        order_repo: OrderRepository,
        cart_repo: CartRepository,
        menu_repo: MenuRepository,
        cafe_repo: CafeRepository,
    ):
        self.order_repo = order_repo
        self.cart_repo = cart_repo
        self.menu_repo = menu_repo
        self.cafe_repo = cafe_repo

    async def create_order_from_cart(
        self,
        cafe_id: str,
        session_id: str,
        table_id: str,
        table_number: str,
        idempotency_key: Optional[str] = None,
        special_instructions: Optional[str] = None,
        customer_name: Optional[str] = None,
        customer_phone: Optional[str] = None,
    ) -> Dict[str, Any]:
        # 1. Idempotency check
        if idempotency_key:
            existing = await self.order_repo.get_by_idempotency_key(cafe_id, idempotency_key)
            if existing:
                logger.info(f"Returning existing order {existing['_id']} for idempotency key {idempotency_key}")
                return existing

        # 2. Fetch cart
        cart_data = await self.cart_repo.get_cart(cafe_id, session_id)
        if not cart_data or not cart_data.get("items"):
            raise ValueError("Cart is empty. Please add items before placing an order.")

        cart = Cart(**cart_data)

        # 3. Authoritative verification of every item price and availability against MongoDB
        item_snapshots: List[OrderItemSnapshot] = []
        authoritative_subtotal = 0

        for cart_item in cart.items:
            db_item = await self.menu_repo.get_item(cafe_id, cart_item.item_id)
            if not db_item:
                raise ValueError(f"Item '{cart_item.name}' is no longer available.")
            if not db_item.get("is_available", True):
                raise ValueError(f"'{db_item['name']}' has just sold out. Please remove it from your cart.")

            # Compute authoritative price
            add_ons_price = sum(a.price_paise for a in cart_item.selected_add_ons)
            authoritative_unit_price = db_item["price_paise"] + add_ons_price
            authoritative_line_total = authoritative_unit_price * cart_item.quantity
            authoritative_subtotal += authoritative_line_total

            item_snapshots.append(
                OrderItemSnapshot(
                    item_id=cart_item.item_id,
                    name=db_item["name"],
                    quantity=cart_item.quantity,
                    unit_price_paise=authoritative_unit_price,
                    selected_add_ons=[a.model_dump() for a in cart_item.selected_add_ons],
                    special_instructions=cart_item.special_instructions,
                    line_total_paise=authoritative_line_total,
                )
            )

        # 4. Determine cafe config and payment mode
        cafe = await self.cafe_repo.get_by_id(cafe_id)
        payment_mode = cafe.get("payment_mode", PaymentMode.PAY_NOW.value) if cafe else PaymentMode.PAY_NOW.value

        if payment_mode == PaymentMode.PAY_NOW.value:
            initial_order_status = OrderStatus.AWAITING_PAYMENT
            initial_payment_status = PaymentStatus.UNPAID
        else:
            initial_order_status = OrderStatus.NEW
            initial_payment_status = PaymentStatus.UNPAID

        # 5. Taxes and final total
        tax_config = cafe.get("tax_config", {}) if cafe else {}
        discount = cart.discount_paise
        taxable_amount = max(0, authoritative_subtotal - discount)
        tax_paise = int((taxable_amount * tax_config.get("gst_rate_percent", 5.0)) / 100) if tax_config.get("gst_enabled") else 0
        sc_paise = int((taxable_amount * tax_config.get("service_charge_percent", 0.0)) / 100) if tax_config.get("service_charge_percent", 0) > 0 else 0
        total_paise = taxable_amount + tax_paise + sc_paise

        now = datetime.now(timezone.utc)
        order_doc: Dict[str, Any] = {
            "cafe_id": cafe_id,
            "table_id": table_id,
            "table_number": table_number,
            "session_id": session_id,
            "order_status": initial_order_status.value,
            "payment_status": initial_payment_status.value,
            "items": [item.model_dump() for item in item_snapshots],
            "subtotal_paise": authoritative_subtotal,
            "discount_paise": discount,
            "tax_paise": tax_paise,
            "service_charge_paise": sc_paise,
            "total_paise": total_paise,
            "special_instructions": special_instructions,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "staff_called": False,
            "idempotency_key": idempotency_key,
            "payments": [],
            "status_history": [
                StatusHistoryEntry(
                    status=f"order:{initial_order_status.value}",
                    actor_type="customer",
                    notes="Order placed by customer",
                    timestamp=now,
                ).model_dump()
            ],
            "created_at": now,
            "updated_at": now,
        }

        order_id = await self.order_repo.insert_one(cafe_id, order_doc)
        order_doc["_id"] = order_id

        # 6. Clear session cart
        await self.cart_repo.clear_cart(cafe_id, session_id)

        return order_doc

    async def transition_order(
        self,
        cafe_id: str,
        order_id: str,
        to_status: OrderStatus,
        actor_type: str,
        actor_id: Optional[str] = None,
        actor_name: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Validates allowed order transitions and executes atomic compare-and-set.
        """
        allowed_transitions: Dict[OrderStatus, List[OrderStatus]] = {
            OrderStatus.AWAITING_PAYMENT: [OrderStatus.NEW, OrderStatus.CANCELLED, OrderStatus.EXPIRED],
            OrderStatus.NEW: [OrderStatus.PREPARING, OrderStatus.CANCELLED],
            OrderStatus.PREPARING: [OrderStatus.READY, OrderStatus.CANCELLED],
            OrderStatus.READY: [OrderStatus.SERVED, OrderStatus.CANCELLED],
            OrderStatus.SERVED: [OrderStatus.COMPLETED],
            OrderStatus.CANCELLED: [],
            OrderStatus.EXPIRED: [],
            OrderStatus.COMPLETED: [],
        }

        # Find which statuses can transition into to_status
        valid_from = [src for src, targets in allowed_transitions.items() if to_status in targets]
        if not valid_from:
            raise ValueError(f"No valid state transition leads to '{to_status.value}'")

        updated = await self.order_repo.atomic_transition_order(
            cafe_id=cafe_id,
            order_id=order_id,
            allowed_from_statuses=valid_from,
            to_status=to_status,
            actor_type=actor_type,
            actor_id=actor_id,
            actor_name=actor_name,
            notes=notes,
        )

        if not updated:
            # Check why it failed
            current = await self.order_repo.get_by_id(cafe_id, order_id)
            if not current:
                raise ValueError("Order not found")
            raise ValueError(
                f"Cannot transition order from '{current.get('order_status')}' to '{to_status.value}'"
            )

        return updated

    async def submit_manual_payment(
        self,
        cafe_id: str,
        order_id: str,
        utr: Optional[str] = None,
        screenshot_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        order = await self.order_repo.get_by_id(cafe_id, order_id)
        if not order:
            raise ValueError("Order not found")

        attempt = PaymentAttempt(
            attempt_id=str(uuid.uuid4())[:8],
            method=PaymentMethod.MANUAL_UPI,
            amount_paise=order["total_paise"],
            utr=utr,
            screenshot_url=screenshot_url,
        )

        updated = await self.order_repo.record_payment_submission(cafe_id, order_id, attempt.model_dump())
        if not updated:
            raise ValueError("Order is not in an unpaid or rejected state for payment submission")
        return updated

    async def verify_payment(
        self,
        cafe_id: str,
        order_id: str,
        is_approved: bool,
        staff_user_id: str,
        rejection_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        updated = await self.order_repo.verify_payment(
            cafe_id=cafe_id,
            order_id=order_id,
            is_approved=is_approved,
            verified_by=staff_user_id,
            rejection_reason=rejection_reason,
        )
        if not updated:
            raise ValueError("Payment cannot be verified (order not in submitted state or already processed)")
        return updated
