from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field


class SelectedAddOn(BaseModel):
    id: str
    name: str
    price_paise: int


class CartItem(BaseModel):
    item_id: str
    name: str
    quantity: int = Field(ge=1)
    unit_price_paise: int = Field(ge=0)
    selected_add_ons: List[SelectedAddOn] = Field(default_factory=list)
    special_instructions: Optional[str] = None
    line_total_paise: int = Field(ge=0)


class Cart(BaseModel):
    session_id: str
    cafe_id: str
    table_id: str
    items: List[CartItem] = Field(default_factory=list)
    subtotal_paise: int = 0
    discount_paise: int = 0
    tax_paise: int = 0
    service_charge_paise: int = 0
    total_paise: int = 0
    applied_deal_code: Optional[str] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AddToCartRequest(BaseModel):
    item_id: str
    quantity: int = 1
    selected_add_ons: List[str] = Field(default_factory=list)  # add-on IDs
    special_instructions: Optional[str] = None


class UpdateCartItemRequest(BaseModel):
    quantity: int = Field(ge=0)  # 0 to remove
    special_instructions: Optional[str] = None


class ApplyDealRequest(BaseModel):
    code: str
