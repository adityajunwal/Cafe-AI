import pytest
from app.modules.cafes.models import PaymentMode
from app.modules.cafes.repository import CafeRepository
from app.modules.cart.repository import CartRepository
from app.modules.cart.service import CartService
from app.modules.menu.repository import DealRepository, MenuRepository
from app.modules.orders.models import OrderStatus, PaymentStatus
from app.modules.orders.repository import OrderRepository
from app.modules.orders.service import OrderService


@pytest.mark.asyncio
async def test_manual_upi_submission_and_staff_approval(async_db, cafe_a_id):
    cafe_repo = CafeRepository(async_db)
    menu_repo = MenuRepository(async_db)
    deal_repo = DealRepository(async_db)
    cart_repo = CartRepository(async_db)
    order_repo = OrderRepository(async_db)

    # Pay-now cafe
    await cafe_repo.create({"_id": cafe_a_id, "name": "UPI Cafe", "payment_mode": PaymentMode.PAY_NOW.value})
    item_id = await menu_repo.create_item(cafe_a_id, {"name": "Cappuccino", "price_paise": 20000, "is_available": True})

    cart_service = CartService(cart_repo, menu_repo, deal_repo, cafe_repo)
    order_service = OrderService(order_repo, cart_repo, menu_repo, cafe_repo)

    await cart_service.add_item_to_cart(cafe_a_id, "sess_upi", "t1", item_id, quantity=1)
    order = await order_service.create_order_from_cart(cafe_a_id, "sess_upi", "t1", "3")
    order_id = str(order["_id"])

    # 1. Initially AwaitingPayment & Unpaid
    assert order["order_status"] == OrderStatus.AWAITING_PAYMENT.value
    assert order["payment_status"] == PaymentStatus.UNPAID.value

    # 2. Customer submits UTR "UTR987654321" and screenshot
    submitted_order = await order_service.submit_manual_payment(
        cafe_id=cafe_a_id,
        order_id=order_id,
        utr="UTR987654321",
        screenshot_url="https://r2.cafe.com/evidence.jpg",
    )

    # Guardrail check: Payment MUST NOT be auto-verified!
    assert submitted_order["payment_status"] == PaymentStatus.SUBMITTED.value
    assert submitted_order["order_status"] == OrderStatus.AWAITING_PAYMENT.value
    assert len(submitted_order["payments"]) == 1
    assert submitted_order["payments"][0]["utr"] == "UTR987654321"

    # 3. Staff verifies in their UPI app and approves
    approved_order = await order_service.verify_payment(
        cafe_id=cafe_a_id,
        order_id=order_id,
        is_approved=True,
        staff_user_id="staff_aditya",
    )

    assert approved_order["payment_status"] == PaymentStatus.VERIFIED.value
    # Order now moved to kitchen New
    assert approved_order["order_status"] == OrderStatus.NEW.value
    assert approved_order["payments"][0]["verified_by"] == "staff_aditya"


@pytest.mark.asyncio
async def test_manual_upi_staff_rejection_allows_retry(async_db, cafe_a_id):
    cafe_repo = CafeRepository(async_db)
    menu_repo = MenuRepository(async_db)
    deal_repo = DealRepository(async_db)
    cart_repo = CartRepository(async_db)
    order_repo = OrderRepository(async_db)

    await cafe_repo.create({"_id": cafe_a_id, "name": "UPI Cafe 2", "payment_mode": PaymentMode.PAY_NOW.value})
    item_id = await menu_repo.create_item(cafe_a_id, {"name": "Latte", "price_paise": 22000, "is_available": True})

    cart_service = CartService(cart_repo, menu_repo, deal_repo, cafe_repo)
    order_service = OrderService(order_repo, cart_repo, menu_repo, cafe_repo)

    await cart_service.add_item_to_cart(cafe_a_id, "sess_upi_rej", "t1", item_id, quantity=1)
    order = await order_service.create_order_from_cart(cafe_a_id, "sess_upi_rej", "t1", "3")
    order_id = str(order["_id"])

    # Customer submits wrong payment
    await order_service.submit_manual_payment(cafe_id=cafe_a_id, order_id=order_id, utr="WRONG123")

    # Staff rejects
    rejected_order = await order_service.verify_payment(
        cafe_id=cafe_a_id,
        order_id=order_id,
        is_approved=False,
        staff_user_id="staff_aditya",
        rejection_reason="Amount not received in soundbox",
    )

    assert rejected_order["payment_status"] == PaymentStatus.REJECTED.value
    assert rejected_order["order_status"] == OrderStatus.AWAITING_PAYMENT.value
    assert rejected_order["payments"][0]["rejection_reason"] == "Amount not received in soundbox"

    # Customer retries with correct UTR
    retried_order = await order_service.submit_manual_payment(cafe_id=cafe_a_id, order_id=order_id, utr="CORRECT999")
    assert retried_order["payment_status"] == PaymentStatus.SUBMITTED.value
