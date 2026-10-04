import pytest
from app.modules.cafes.repository import CafeRepository
from app.modules.cart.repository import CartRepository
from app.modules.cart.service import CartService
from app.modules.menu.repository import DealRepository, MenuRepository
from app.modules.orders.models import OrderStatus
from app.modules.orders.repository import OrderRepository
from app.modules.orders.service import OrderService


@pytest.mark.asyncio
async def test_order_valid_lifecycle_transitions(async_db, cafe_a_id):
    cafe_repo = CafeRepository(async_db)
    menu_repo = MenuRepository(async_db)
    deal_repo = DealRepository(async_db)
    cart_repo = CartRepository(async_db)
    order_repo = OrderRepository(async_db)

    await cafe_repo.create({"_id": cafe_a_id, "name": "Lifecycle Cafe", "payment_mode": "pay_after"})

    item_id = await menu_repo.create_item(cafe_a_id, {
        "name": "Croissant",
        "price_paise": 15000,
        "is_available": True,
    })

    cart_service = CartService(cart_repo, menu_repo, deal_repo, cafe_repo)
    order_service = OrderService(order_repo, cart_repo, menu_repo, cafe_repo)

    await cart_service.add_item_to_cart(cafe_a_id, "sess_order_trans", "t1", item_id, quantity=1)
    order = await order_service.create_order_from_cart(cafe_a_id, "sess_order_trans", "t1", "1")
    order_id = str(order["_id"])

    # Initial in pay_after is NEW
    assert order["order_status"] == OrderStatus.NEW.value

    # NEW -> PREPARING
    o1 = await order_service.transition_order(cafe_a_id, order_id, OrderStatus.PREPARING, actor_type="staff")
    assert o1["order_status"] == OrderStatus.PREPARING.value

    # PREPARING -> READY
    o2 = await order_service.transition_order(cafe_a_id, order_id, OrderStatus.READY, actor_type="staff")
    assert o2["order_status"] == OrderStatus.READY.value

    # READY -> SERVED
    o3 = await order_service.transition_order(cafe_a_id, order_id, OrderStatus.SERVED, actor_type="staff")
    assert o3["order_status"] == OrderStatus.SERVED.value

    # SERVED -> COMPLETED
    o4 = await order_service.transition_order(cafe_a_id, order_id, OrderStatus.COMPLETED, actor_type="staff")
    assert o4["order_status"] == OrderStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_order_invalid_transitions_rejected(async_db, cafe_a_id):
    cafe_repo = CafeRepository(async_db)
    menu_repo = MenuRepository(async_db)
    deal_repo = DealRepository(async_db)
    cart_repo = CartRepository(async_db)
    order_repo = OrderRepository(async_db)

    await cafe_repo.create({"_id": cafe_a_id, "name": "Invalid Trans Cafe", "payment_mode": "pay_after"})

    item_id = await menu_repo.create_item(cafe_a_id, {
        "name": "Tea",
        "price_paise": 5000,
        "is_available": True,
    })

    cart_service = CartService(cart_repo, menu_repo, deal_repo, cafe_repo)
    order_service = OrderService(order_repo, cart_repo, menu_repo, cafe_repo)

    await cart_service.add_item_to_cart(cafe_a_id, "sess_invalid_trans", "t1", item_id, quantity=1)
    order = await order_service.create_order_from_cart(cafe_a_id, "sess_invalid_trans", "t1", "1")
    order_id = str(order["_id"])

    # Cannot skip directly from NEW to SERVED
    with pytest.raises(ValueError, match="Cannot transition order"):
        await order_service.transition_order(cafe_a_id, order_id, OrderStatus.SERVED, actor_type="staff")

    # Cancel order
    await order_service.transition_order(cafe_a_id, order_id, OrderStatus.CANCELLED, actor_type="staff")

    # Cancelled order CANNOT be moved back to PREPARING
    with pytest.raises(ValueError):
        await order_service.transition_order(cafe_a_id, order_id, OrderStatus.PREPARING, actor_type="staff")


@pytest.mark.asyncio
async def test_order_creation_idempotency(async_db, cafe_a_id):
    cafe_repo = CafeRepository(async_db)
    menu_repo = MenuRepository(async_db)
    deal_repo = DealRepository(async_db)
    cart_repo = CartRepository(async_db)
    order_repo = OrderRepository(async_db)

    await cafe_repo.create({"_id": cafe_a_id, "name": "Idempotent Cafe"})
    item_id = await menu_repo.create_item(cafe_a_id, {"name": "Burger", "price_paise": 18000, "is_available": True})

    cart_service = CartService(cart_repo, menu_repo, deal_repo, cafe_repo)
    order_service = OrderService(order_repo, cart_repo, menu_repo, cafe_repo)

    await cart_service.add_item_to_cart(cafe_a_id, "sess_idem", "t1", item_id, quantity=1)

    idempotency_key = "unique-key-submit-12345"
    order1 = await order_service.create_order_from_cart(
        cafe_id=cafe_a_id,
        session_id="sess_idem",
        table_id="t1",
        table_number="1",
        idempotency_key=idempotency_key,
    )

    # Re-submitting with the same idempotency key returns the same order without error or duplication
    order2 = await order_service.create_order_from_cart(
        cafe_id=cafe_a_id,
        session_id="sess_idem",
        table_id="t1",
        table_number="1",
        idempotency_key=idempotency_key,
    )

    assert str(order1["_id"]) == str(order2["_id"])
