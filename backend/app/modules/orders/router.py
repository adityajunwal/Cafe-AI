from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from app.database import get_database
from app.modules.auth_tenancy.dependencies import get_current_user, get_customer_session, require_roles
from app.modules.auth_tenancy.models import CustomerSessionInfo, StaffUserResponse, UserRole
from app.modules.cafes.repository import CafeRepository
from app.modules.cart.repository import CartRepository
from app.modules.menu.repository import MenuRepository
from app.modules.orders.models import (
    OrderCreate,
    OrderResponse,
    OrderTransitionRequest,
    PaymentSubmissionRequest,
    PaymentVerificationRequest,
)
from app.modules.orders.repository import OrderRepository
from app.modules.orders.service import OrderService
from app.modules.realtime.event_bus import EventBus

router = APIRouter(prefix="/v1", tags=["Orders & Kanban"])


def get_order_service(db=Depends(get_database)) -> OrderService:
    return OrderService(
        order_repo=OrderRepository(db),
        cart_repo=CartRepository(db),
        menu_repo=MenuRepository(db),
        cafe_repo=CafeRepository(db),
    )


@router.post("/orders", response_model=OrderResponse)
async def create_order(
    data: OrderCreate,
    session: CustomerSessionInfo = Depends(get_customer_session),
    order_service: OrderService = Depends(get_order_service),
    db=Depends(get_database),
):
    try:
        order = await order_service.create_order_from_cart(
            cafe_id=session.cafe_id,
            session_id=session.session_id,
            table_id=session.table_id,
            table_number=session.table_number,
            idempotency_key=data.idempotency_key,
            special_instructions=data.special_instructions,
            customer_name=data.customer_name,
            customer_phone=data.customer_phone,
        )

        event_bus = EventBus(db)
        await event_bus.publish(
            cafe_id=session.cafe_id,
            event_type="order.created",
            data={
                "order_id": str(order["_id"]),
                "table_number": session.table_number,
                "total_paise": order["total_paise"],
                "order_status": order["order_status"],
                "payment_status": order["payment_status"],
                "session_id": session.session_id,
            },
        )

        order["id"] = str(order["_id"])
        return OrderResponse(**order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    session: CustomerSessionInfo = Depends(get_customer_session),
    db=Depends(get_database),
):
    repo = OrderRepository(db)
    order = await repo.get_by_id(session.cafe_id, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    order["id"] = str(order["_id"])
    return OrderResponse(**order)


@router.get("/orders", response_model=List[OrderResponse])
async def list_session_orders(
    session: CustomerSessionInfo = Depends(get_customer_session),
    db=Depends(get_database),
):
    repo = OrderRepository(db)
    orders = await repo.get_active_orders_for_session(session.cafe_id, session.session_id)
    for o in orders:
        o["id"] = str(o["_id"])
    return [OrderResponse(**o) for o in orders]


@router.post("/orders/{order_id}/payment-submission", response_model=OrderResponse)
async def submit_payment(
    order_id: str,
    data: PaymentSubmissionRequest,
    session: CustomerSessionInfo = Depends(get_customer_session),
    order_service: OrderService = Depends(get_order_service),
    db=Depends(get_database),
):
    try:
        updated = await order_service.submit_manual_payment(
            cafe_id=session.cafe_id,
            order_id=order_id,
            utr=data.utr,
            screenshot_url=data.screenshot_url,
        )

        event_bus = EventBus(db)
        await event_bus.publish(
            cafe_id=session.cafe_id,
            event_type="payment.submitted",
            data={
                "order_id": order_id,
                "table_number": updated.get("table_number"),
                "utr": data.utr,
                "amount_paise": updated.get("total_paise"),
            },
        )

        updated["id"] = str(updated["_id"])
        return OrderResponse(**updated)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/orders/{order_id}/verify-payment", response_model=OrderResponse)
async def verify_payment(
    order_id: str,
    data: PaymentVerificationRequest,
    current_user: StaffUserResponse = Depends(require_roles(UserRole.STAFF, UserRole.OWNER)),
    order_service: OrderService = Depends(get_order_service),
    db=Depends(get_database),
):
    is_approved = data.action.lower().strip() == "approve"
    try:
        updated = await order_service.verify_payment(
            cafe_id=current_user.cafe_id,
            order_id=order_id,
            is_approved=is_approved,
            staff_user_id=current_user.id,
            rejection_reason=data.rejection_reason,
        )

        event_bus = EventBus(db)
        event_type = "payment.approved" if is_approved else "payment.rejected"
        await event_bus.publish(
            cafe_id=current_user.cafe_id,
            event_type=event_type,
            data={
                "order_id": order_id,
                "session_id": updated.get("session_id"),
                "order_status": updated.get("order_status"),
                "payment_status": updated.get("payment_status"),
                "rejection_reason": data.rejection_reason,
            },
        )

        updated["id"] = str(updated["_id"])
        return OrderResponse(**updated)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/orders/{order_id}/transition", response_model=OrderResponse)
async def transition_order(
    order_id: str,
    data: OrderTransitionRequest,
    current_user: StaffUserResponse = Depends(require_roles(UserRole.STAFF, UserRole.OWNER)),
    order_service: OrderService = Depends(get_order_service),
    db=Depends(get_database),
):
    try:
        updated = await order_service.transition_order(
            cafe_id=current_user.cafe_id,
            order_id=order_id,
            to_status=data.to_status,
            actor_type="staff",
            actor_id=current_user.id,
            actor_name=current_user.name,
            notes=data.notes,
        )

        event_bus = EventBus(db)
        await event_bus.publish(
            cafe_id=current_user.cafe_id,
            event_type="order.status_changed",
            data={
                "order_id": order_id,
                "session_id": updated.get("session_id"),
                "order_status": updated.get("order_status"),
                "to_status": data.to_status.value,
            },
        )

        updated["id"] = str(updated["_id"])
        return OrderResponse(**updated)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/board")
async def get_kanban_board(
    current_user: StaffUserResponse = Depends(get_current_user),
    db=Depends(get_database),
):
    """Staff Kanban board: lists active orders with authoritative sequence number for resync."""
    repo = OrderRepository(db)
    orders = await repo.get_kanban_orders(current_user.cafe_id)

    counter = await db.counters.find_one({"cafe_id": current_user.cafe_id, "key": "event_seq"})
    as_of_seq = counter.get("seq", 0) if counter else 0

    for o in orders:
        o["id"] = str(o.pop("_id", o.get("id", "")))

    return {
        "as_of_seq": as_of_seq,
        "orders": orders,
    }
