import pytest
from app.modules.auth_tenancy.repository import TenantRepository


@pytest.mark.asyncio
async def test_tenant_repository_requires_valid_cafe_id(async_db):
    repo = TenantRepository(async_db, "test_collection")

    with pytest.raises(ValueError, match="cafe_id is required"):
        await repo.insert_one("", {"name": "invalid"})

    with pytest.raises(ValueError, match="cafe_id is required"):
        await repo.find_one(None, {"name": "invalid"})

    with pytest.raises(ValueError, match="cafe_id is required"):
        await repo.find_all("", {})


@pytest.mark.asyncio
async def test_cross_tenant_read_isolation(async_db, cafe_a_id, cafe_b_id):
    repo = TenantRepository(async_db, "menu_items")

    # Cafe A inserts a secret recipe
    doc_id = await repo.insert_one(cafe_a_id, {"name": "Cafe A Special Coffee", "price_paise": 25000})

    # Cafe A can find it
    found_a = await repo.find_by_id(cafe_a_id, doc_id)
    assert found_a is not None
    assert found_a["name"] == "Cafe A Special Coffee"

    # Cafe B MUST NOT find it
    found_b = await repo.find_by_id(cafe_b_id, doc_id)
    assert found_b is None

    # Cafe B query all must return empty
    all_b = await repo.find_all(cafe_b_id, {})
    assert len(all_b) == 0


@pytest.mark.asyncio
async def test_cross_tenant_update_isolation(async_db, cafe_a_id, cafe_b_id):
    repo = TenantRepository(async_db, "orders")

    # Order created for Cafe A
    order_id = await repo.insert_one(cafe_a_id, {"total_paise": 50000, "status": "new"})

    # Cafe B attempts to modify Cafe A's order
    mod_count = await repo.update_one(cafe_b_id, {"_id": order_id}, {"$set": {"status": "cancelled"}})
    assert mod_count == 0

    # Verify Cafe A's order remained untouched
    order_a = await repo.find_by_id(cafe_a_id, order_id)
    assert order_a["status"] == "new"


@pytest.mark.asyncio
async def test_cross_tenant_delete_isolation(async_db, cafe_a_id, cafe_b_id):
    repo = TenantRepository(async_db, "tables")

    # Table created for Cafe A
    table_id = await repo.insert_one(cafe_a_id, {"number": "1", "capacity": 4})

    # Cafe B attempts to delete Cafe A's table
    del_count = await repo.delete_one(cafe_b_id, {"_id": table_id})
    assert del_count == 0

    # Verify table still exists in Cafe A
    table_a = await repo.find_by_id(cafe_a_id, table_id)
    assert table_a is not None
