from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from app.database import get_database
from app.modules.auth_tenancy.dependencies import get_current_user, require_roles
from app.modules.auth_tenancy.models import StaffUserResponse, UserRole
from app.modules.cafes.models import CafeResponse, CafeUpdate, TableCreate, TableResponse
from app.modules.cafes.repository import CafeRepository, TableRepository

router = APIRouter(prefix="/v1", tags=["Cafes & Tables"])


@router.get("/cafes/me", response_model=CafeResponse)
async def get_my_cafe(
    current_user: StaffUserResponse = Depends(get_current_user),
    db=Depends(get_database),
):
    repo = CafeRepository(db)
    cafe = await repo.get_by_id(current_user.cafe_id)
    if not cafe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cafe not found")
    cafe["id"] = str(cafe["_id"])
    return CafeResponse(**cafe)


@router.patch("/cafes/settings", response_model=CafeResponse)
async def update_cafe_settings(
    updates: CafeUpdate,
    current_user: StaffUserResponse = Depends(require_roles(UserRole.OWNER, UserRole.PLATFORM_ADMIN)),
    db=Depends(get_database),
):
    repo = CafeRepository(db)
    update_data = updates.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided for update")

    success = await repo.update(current_user.cafe_id, update_data)
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Update failed")

    updated = await repo.get_by_id(current_user.cafe_id)
    updated["id"] = str(updated["_id"])
    return CafeResponse(**updated)


@router.post("/tables", response_model=TableResponse)
async def create_table(
    data: TableCreate,
    current_user: StaffUserResponse = Depends(require_roles(UserRole.OWNER, UserRole.STAFF)),
    db=Depends(get_database),
):
    repo = TableRepository(db)
    existing = await repo.get_by_number(current_user.cafe_id, data.number)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Table number '{data.number}' already exists",
        )

    table_id = await repo.create_table(current_user.cafe_id, data.model_dump())
    table_doc = await repo.find_by_id(current_user.cafe_id, table_id)
    table_doc["id"] = str(table_doc["_id"])
    return TableResponse(**table_doc)


@router.get("/tables", response_model=List[TableResponse])
async def list_tables(
    current_user: StaffUserResponse = Depends(get_current_user),
    db=Depends(get_database),
):
    repo = TableRepository(db)
    tables = await repo.find_all(current_user.cafe_id, sort=[("number", 1)])
    for t in tables:
        t["id"] = str(t["_id"])
    return [TableResponse(**t) for t in tables]
