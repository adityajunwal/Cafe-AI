import pytest
from app.modules.bills.service import BillService
from app.modules.cafes.models import TaxConfig
from app.modules.cafes.repository import CafeRepository
from app.modules.cart.repository import CartRepository
from app.modules.cart.service import CartService
from app.modules.menu.repository import DealRepository, MenuRepository
from app.modules.orders.repository import OrderRepository
from app.modules.orders.service import OrderService


@pytest.mark.asyncio
async def test_paise_arithmetic_in_cart_and_bills(async_db, cafe_a_id):
    cafe_repo = CafeRepository(async_db)
    menu_repo = MenuRepository(async_db)
    deal_repo = DealRepository(async_db)
    cart_repo = CartRepository(async_db)
    order_repo = OrderRepository(async_db)

    # 1. Setup Cafe A with 5% GST and 10% Service Charge
    await cafe_repo.create({
        "_id": cafe_a_id,
        "name": "Artisan Roastery",
        "tax_config": TaxConfig(
            gst_enabled=True,
            gst_rate_percent=5.0,
            service_charge_percent=10.0,
            gstin="07AAAAA0000A1Z5",
        ).model_dump(),
    })

    # 2. Add menu item: Cold Brew (₹250.00 = 25000 paise) with Almond Milk add-on (₹40.00 = 4000 paise)
    item_id = await menu_repo.create_item(cafe_a_id, {
        "name": "Signature Cold Brew",
        "price_paise": 25000,
        "is_available": True,
        "add_ons": [{"id": "addon_almond", "name": "Almond Milk", "price_paise": 4000}],
    })

    cart_service = CartService(cart_repo, menu_repo, deal_repo, cafe_repo)

    # 3. Add 2 Cold Brews with Almond Milk:
    # Unit price = 25000 + 4000 = 29000 paise
    # Subtotal = 29000 * 2 = 58000 paise
    session_id = "test_money_sess"
    cart = await cart_service.add_item_to_cart(
        cafe_id=cafe_a_id,
        session_id=session_id,
        table_id="table_1",
        item_id=item_id,
        quantity=2,
        selected_add_on_ids=["addon_almond"],
    )

    assert cart.subtotal_paise == 58000
    # Tax: 5% of 58000 = 2900 paise
    assert cart.tax_paise == 2900
    # Service charge: 10% of 58000 = 5800 paise
    assert cart.service_charge_paise == 5800
    # Total: 58000 + 2900 + 5800 = 66700 paise (₹667.00)
    assert cart.total_paise == 66700

    # 4. Convert cart to order
    order_service = OrderService(order_repo, cart_repo, menu_repo, cafe_repo)
    order = await order_service.create_order_from_cart(
        cafe_id=cafe_a_id,
        session_id=session_id,
        table_id="table_1",
        table_number="5",
    )

    assert order["subtotal_paise"] == 58000
    assert order["total_paise"] == 66700
    assert order["items"][0]["unit_price_paise"] == 29000
    assert order["items"][0]["line_total_paise"] == 58000

    # 5. Generate Bill
    bill_service = BillService(async_db, order_repo, cafe_repo)
    bill = await bill_service.get_or_generate_bill(cafe_a_id, str(order["_id"]))

    assert bill["total_paise"] == 66700
    assert bill["tax_breakdown"]["cgst_paise"] == 1450  # 2.5% of 58000
    assert bill["tax_breakdown"]["sgst_paise"] == 1450  # 2.5% of 58000
    assert bill["tax_breakdown"]["service_charge_paise"] == 5800
    assert bill["bill_number"].startswith("FY")


@pytest.mark.asyncio
async def test_order_snapshot_immutability(async_db, cafe_a_id):
    """
    Mandatory rule: Later menu edits must NOT change existing orders or bills!
    """
    cafe_repo = CafeRepository(async_db)
    menu_repo = MenuRepository(async_db)
    deal_repo = DealRepository(async_db)
    cart_repo = CartRepository(async_db)
    order_repo = OrderRepository(async_db)

    await cafe_repo.create({"_id": cafe_a_id, "name": "Cafe Snapshot Test"})

    # Create item at ₹100.00 (10000 paise)
    item_id = await menu_repo.create_item(cafe_a_id, {
        "name": "Espresso",
        "price_paise": 10000,
        "is_available": True,
    })

    cart_service = CartService(cart_repo, menu_repo, deal_repo, cafe_repo)
    order_service = OrderService(order_repo, cart_repo, menu_repo, cafe_repo)

    await cart_service.add_item_to_cart(cafe_a_id, "sess_snap", "t1", item_id, quantity=1)
    order = await order_service.create_order_from_cart(cafe_a_id, "sess_snap", "t1", "1")

    assert order["total_paise"] == 10000

    # Owner now doubles the price to ₹200.00 (20000 paise)
    await menu_repo.update_item(cafe_a_id, item_id, {"price_paise": 20000})

    # The existing order MUST STILL have the original price 10000 paise
    fetched_order = await order_repo.get_by_id(cafe_a_id, str(order["_id"]))
    assert fetched_order["total_paise"] == 10000
    assert fetched_order["items"][0]["unit_price_paise"] == 10000
