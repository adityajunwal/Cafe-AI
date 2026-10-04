import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.database import get_database
from app.modules.cafes.repository import CafeRepository, TableRepository
from app.modules.menu.repository import MenuRepository


@pytest.mark.asyncio
async def test_full_api_ordering_journey(async_db, cafe_a_id):
    # Override database dependency with mock db
    app.dependency_overrides[get_database] = lambda: async_db

    try:
        cafe_repo = CafeRepository(async_db)
        table_repo = TableRepository(async_db)
        menu_repo = MenuRepository(async_db)

        # 1. Seed cafe, table, and menu item
        await cafe_repo.create({"_id": cafe_a_id, "name": "API Test Cafe", "payment_mode": "pay_after"})
        table_id = await table_repo.create_table(cafe_a_id, {"number": "7"})
        table_doc = await table_repo.find_by_id(cafe_a_id, table_id)
        qr_token = table_doc["qr_token"]

        item_id = await menu_repo.create_item(cafe_a_id, {
            "name": "Iced Americano",
            "price_paise": 18000,
            "category": "Coffee",
            "is_available": True,
            "status": "published",
        })

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Health
            res = await client.get("/health")
            assert res.status_code == 200
            assert res.json()["status"] == "healthy"

            # 2. Customer scans QR code -> creates session
            res = await client.post("/v1/sessions", json={"qr_token": qr_token})
            assert res.status_code == 200
            session_data = res.json()
            session_token = session_data["session_token"]
            assert session_data["table_number"] == "7"

            headers = {"X-Customer-Session": session_token}

            # 3. Customer views menu (fallback)
            res = await client.get("/v1/menu", headers=headers)
            assert res.status_code == 200
            menu_data = res.json()
            assert len(menu_data["items"]) == 1
            assert menu_data["items"][0]["name"] == "Iced Americano"

            # 4. Add item to cart
            res = await client.post("/v1/cart/items", json={"item_id": item_id, "quantity": 2}, headers=headers)
            assert res.status_code == 200
            cart_data = res.json()
            assert cart_data["subtotal_paise"] == 36000
            assert len(cart_data["items"]) == 1

            # 5. Place order
            res = await client.post("/v1/orders", json={"special_instructions": "Less ice"}, headers=headers)
            assert res.status_code == 200
            order_data = res.json()
            order_id = order_data["id"]
            assert order_data["total_paise"] == 36000
            assert order_data["order_status"] == "new"

            # 6. Fetch bill
            res = await client.get(f"/v1/bills/{order_id}", headers=headers)
            assert res.status_code == 200
            bill_data = res.json()
            assert bill_data["total_paise"] == 36000
            assert bill_data["bill_number"].startswith("FY")

    finally:
        app.dependency_overrides.clear()
