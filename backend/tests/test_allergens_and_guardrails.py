import pytest
from app.modules.ai_waiter.tools import AIWaiterToolExecutor
from app.modules.cafes.repository import CafeRepository
from app.modules.cart.repository import CartRepository
from app.modules.cart.service import CartService
from app.modules.menu.models import AllergenInfo
from app.modules.menu.repository import DealRepository, MenuRepository
from app.modules.orders.repository import OrderRepository
from app.modules.orders.service import OrderService
from app.modules.realtime.event_bus import EventBus


@pytest.mark.asyncio
async def test_allergen_unverified_returns_unknown_and_disclaimer(async_db, cafe_a_id):
    cafe_repo = CafeRepository(async_db)
    menu_repo = MenuRepository(async_db)
    deal_repo = DealRepository(async_db)
    cart_repo = CartRepository(async_db)
    order_repo = OrderRepository(async_db)
    event_bus = EventBus(async_db)

    # Item with UNVERIFIED allergen data (e.g. AI draft during onboarding)
    item_id = await menu_repo.create_item(cafe_a_id, {
        "name": "Walnut Brownie (Draft)",
        "price_paise": 12000,
        "allergens": AllergenInfo(
            contains=["tree_nuts", "dairy"],
            is_verified=False,  # Unverified!
        ).model_dump(),
    })

    cart_service = CartService(cart_repo, menu_repo, deal_repo, cafe_repo)
    order_service = OrderService(order_repo, cart_repo, menu_repo, cafe_repo)

    executor = AIWaiterToolExecutor(
        cafe_id=cafe_a_id,
        session_id="sess_allergen",
        table_id="t1",
        table_number="2",
        menu_repo=menu_repo,
        deal_repo=deal_repo,
        cart_service=cart_service,
        order_service=order_service,
        cafe_repo=cafe_repo,
        event_bus=event_bus,
    )

    result = await executor.execute("get_allergens", {"item_id": item_id})

    # Guardrail check: Must NOT report safe or verified allergens!
    assert result["is_verified"] is False
    assert result["contains_allergens"] == "Unknown / Unverified"
    assert "NOT been verified" in result["backend_disclaimer"]
    assert "confirm with staff" in result["backend_disclaimer"]


@pytest.mark.asyncio
async def test_allergen_verified_returns_accurate_data(async_db, cafe_a_id):
    cafe_repo = CafeRepository(async_db)
    menu_repo = MenuRepository(async_db)
    deal_repo = DealRepository(async_db)
    cart_repo = CartRepository(async_db)
    order_repo = OrderRepository(async_db)
    event_bus = EventBus(async_db)

    # Item with VERIFIED allergen data (owner confirmed)
    item_id = await menu_repo.create_item(cafe_a_id, {
        "name": "Peanut Butter Toast",
        "price_paise": 15000,
        "allergens": AllergenInfo(
            contains=["peanuts", "gluten"],
            is_verified=True,
            verified_by="owner_1",
        ).model_dump(),
    })

    cart_service = CartService(cart_repo, menu_repo, deal_repo, cafe_repo)
    order_service = OrderService(order_repo, cart_repo, menu_repo, cafe_repo)

    executor = AIWaiterToolExecutor(
        cafe_id=cafe_a_id,
        session_id="sess_allergen_ver",
        table_id="t1",
        table_number="2",
        menu_repo=menu_repo,
        deal_repo=deal_repo,
        cart_service=cart_service,
        order_service=order_service,
        cafe_repo=cafe_repo,
        event_bus=event_bus,
    )

    result = await executor.execute("get_allergens", {"item_id": item_id})

    assert result["is_verified"] is True
    assert "peanuts" in result["contains_allergens"]
    assert "gluten" in result["contains_allergens"]


@pytest.mark.asyncio
async def test_sold_out_item_cannot_be_ordered(async_db, cafe_a_id):
    cafe_repo = CafeRepository(async_db)
    menu_repo = MenuRepository(async_db)
    deal_repo = DealRepository(async_db)
    cart_repo = CartRepository(async_db)

    item_id = await menu_repo.create_item(cafe_a_id, {
        "name": "Matcha Cheesecake",
        "price_paise": 22000,
        "is_available": False,  # Sold out!
    })

    cart_service = CartService(cart_repo, menu_repo, deal_repo, cafe_repo)

    with pytest.raises(ValueError, match="currently sold out"):
        await cart_service.add_item_to_cart(cafe_a_id, "sess_sold", "t1", item_id, quantity=1)
