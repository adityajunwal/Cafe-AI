from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.database import get_database
from app.modules.auth_tenancy.dependencies import get_current_user, get_customer_session, require_roles
from app.modules.auth_tenancy.models import CustomerSessionInfo, StaffUserResponse, UserRole
from app.modules.cafes.repository import CafeRepository
from app.modules.menu.models import (
    DealCreate,
    DealResponse,
    MenuCategoryCreate,
    MenuCategoryResponse,
    MenuItemCreate,
    MenuItemResponse,
    MenuItemUpdate,
)
from app.modules.menu.repository import DealRepository, MenuCategoryRepository, MenuRepository

router = APIRouter(prefix="/v1", tags=["Menu & Deals"])


@router.get("/menu")
async def get_menu(
    session: CustomerSessionInfo = Depends(get_customer_session),
    db=Depends(get_database),
):
    """Customer manual menu view (fallback). Shows published categories, items, and active deals."""
    menu_repo = MenuRepository(db)
    cat_repo = MenuCategoryRepository(db)
    deal_repo = DealRepository(db)

    items = await menu_repo.get_published_menu(session.cafe_id)
    categories = await cat_repo.get_categories(session.cafe_id)
    deals = await deal_repo.get_active_deals(session.cafe_id)

    for i in items:
        i["id"] = str(i.pop("_id", i.get("id", "")))
    for c in categories:
        c["id"] = str(c.pop("_id", c.get("id", "")))
    for d in deals:
        d["id"] = str(d.pop("_id", d.get("id", "")))

    return {
        "cafe_id": session.cafe_id,
        "table_number": session.table_number,
        "categories": categories,
        "items": items,
        "deals": deals,
    }


@router.post("/menu/items", response_model=MenuItemResponse)
async def create_menu_item(
    data: MenuItemCreate,
    current_user: StaffUserResponse = Depends(require_roles(UserRole.OWNER, UserRole.STAFF)),
    db=Depends(get_database),
):
    menu_repo = MenuRepository(db)
    cafe_repo = CafeRepository(db)

    item_id = await menu_repo.create_item(current_user.cafe_id, data.model_dump())
    await cafe_repo.bump_cache_version(current_user.cafe_id)

    item_doc = await menu_repo.get_item(current_user.cafe_id, item_id)
    item_doc["id"] = str(item_doc["_id"])
    return MenuItemResponse(**item_doc)


@router.patch("/menu/items/{item_id}", response_model=MenuItemResponse)
async def update_menu_item(
    item_id: str,
    updates: MenuItemUpdate,
    current_user: StaffUserResponse = Depends(require_roles(UserRole.OWNER, UserRole.STAFF)),
    db=Depends(get_database),
):
    menu_repo = MenuRepository(db)
    cafe_repo = CafeRepository(db)

    upd_dict = updates.model_dump(exclude_unset=True)
    if not upd_dict:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No update fields specified")

    success = await menu_repo.update_item(current_user.cafe_id, item_id, upd_dict)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found")

    await cafe_repo.bump_cache_version(current_user.cafe_id)

    updated_doc = await menu_repo.get_item(current_user.cafe_id, item_id)
    updated_doc["id"] = str(updated_doc["_id"])
    return MenuItemResponse(**updated_doc)


@router.post("/menu/categories", response_model=MenuCategoryResponse)
async def create_category(
    data: MenuCategoryCreate,
    current_user: StaffUserResponse = Depends(require_roles(UserRole.OWNER, UserRole.STAFF)),
    db=Depends(get_database),
):
    cat_repo = MenuCategoryRepository(db)
    cat_id = await cat_repo.create_category(current_user.cafe_id, data.model_dump())
    cat_doc = await cat_repo.find_by_id(current_user.cafe_id, cat_id)
    cat_doc["id"] = str(cat_doc["_id"])
    return MenuCategoryResponse(**cat_doc)


@router.post("/menu/deals", response_model=DealResponse)
async def create_deal(
    data: DealCreate,
    current_user: StaffUserResponse = Depends(require_roles(UserRole.OWNER, UserRole.STAFF)),
    db=Depends(get_database),
):
    deal_repo = DealRepository(db)
    deal_id = await deal_repo.insert_one(current_user.cafe_id, data.model_dump())
    deal_doc = await deal_repo.find_by_id(current_user.cafe_id, deal_id)
    deal_doc["id"] = str(deal_doc["_id"])
    return DealResponse(**deal_doc)
