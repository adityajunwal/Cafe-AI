from fastapi import APIRouter, Depends, HTTPException, status
from app.database import get_database
from app.modules.auth_tenancy.dependencies import get_customer_session
from app.modules.auth_tenancy.models import CustomerSessionInfo
from app.modules.cafes.repository import CafeRepository
from app.modules.cart.models import AddToCartRequest, ApplyDealRequest, Cart, UpdateCartItemRequest
from app.modules.cart.repository import CartRepository
from app.modules.cart.service import CartService
from app.modules.menu.repository import DealRepository, MenuRepository

router = APIRouter(prefix="/v1/cart", tags=["Cart"])


def get_cart_service(db=Depends(get_database)) -> CartService:
    return CartService(
        cart_repo=CartRepository(db),
        menu_repo=MenuRepository(db),
        deal_repo=DealRepository(db),
        cafe_repo=CafeRepository(db),
    )


@router.get("", response_model=Cart)
async def get_cart(
    session: CustomerSessionInfo = Depends(get_customer_session),
    service: CartService = Depends(get_cart_service),
):
    return await service.get_or_create_cart(session.cafe_id, session.session_id, session.table_id)


@router.post("/items", response_model=Cart)
async def add_item_to_cart(
    data: AddToCartRequest,
    session: CustomerSessionInfo = Depends(get_customer_session),
    service: CartService = Depends(get_cart_service),
):
    try:
        return await service.add_item_to_cart(
            cafe_id=session.cafe_id,
            session_id=session.session_id,
            table_id=session.table_id,
            item_id=data.item_id,
            quantity=data.quantity,
            selected_add_on_ids=data.selected_add_ons,
            special_instructions=data.special_instructions,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/items/{item_id}", response_model=Cart)
async def update_cart_item(
    item_id: str,
    data: UpdateCartItemRequest,
    session: CustomerSessionInfo = Depends(get_customer_session),
    service: CartService = Depends(get_cart_service),
):
    return await service.update_cart_item(
        cafe_id=session.cafe_id,
        session_id=session.session_id,
        table_id=session.table_id,
        item_id=item_id,
        quantity=data.quantity,
        special_instructions=data.special_instructions,
    )


@router.delete("/items/{item_id}", response_model=Cart)
async def remove_cart_item(
    item_id: str,
    session: CustomerSessionInfo = Depends(get_customer_session),
    service: CartService = Depends(get_cart_service),
):
    return await service.remove_item_from_cart(
        cafe_id=session.cafe_id,
        session_id=session.session_id,
        table_id=session.table_id,
        item_id=item_id,
    )


@router.post("/apply-deal", response_model=Cart)
async def apply_deal(
    data: ApplyDealRequest,
    session: CustomerSessionInfo = Depends(get_customer_session),
    service: CartService = Depends(get_cart_service),
):
    try:
        return await service.apply_deal(
            cafe_id=session.cafe_id,
            session_id=session.session_id,
            table_id=session.table_id,
            code=data.code,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
