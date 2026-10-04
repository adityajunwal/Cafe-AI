from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class AllergenType(str, Enum):
    PEANUTS = "peanuts"
    TREE_NUTS = "tree_nuts"
    DAIRY = "dairy"
    GLUTEN = "gluten"
    EGGS = "eggs"
    SOY = "soy"
    FISH = "fish"
    SHELLFISH = "shellfish"
    MUSTARD = "mustard"
    SESAME = "sesame"


class AllergenInfo(BaseModel):
    contains: List[str] = Field(default_factory=list)
    is_verified: bool = False
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None
    notes: Optional[str] = None
    disclaimer: str = (
        "Allergen information is based on cafe-provided verified data. "
        "For severe allergies, always confirm directly with our staff."
    )


class AddOnOption(BaseModel):
    id: str
    name: str
    price_paise: int  # in paise


class MenuItemStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class MenuItemBase(BaseModel):
    name: str
    description: str = ""
    category: str
    price_paise: int = Field(ge=0, description="Price in Indian Paise (e.g., 25000 = Rs 250.00)")
    is_available: bool = True
    is_promoted: bool = False
    dietary_tags: List[str] = Field(default_factory=list)  # ["veg", "vegan", "non-veg", "jain"]
    allergens: AllergenInfo = Field(default_factory=AllergenInfo)
    add_ons: List[AddOnOption] = Field(default_factory=list)
    image_url: Optional[str] = None
    status: MenuItemStatus = MenuItemStatus.PUBLISHED


class MenuItemCreate(MenuItemBase):
    pass


class MenuItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    price_paise: Optional[int] = Field(default=None, ge=0)
    is_available: Optional[bool] = None
    is_promoted: Optional[bool] = None
    dietary_tags: Optional[List[str]] = None
    allergens: Optional[AllergenInfo] = None
    add_ons: Optional[List[AddOnOption]] = None
    image_url: Optional[str] = None
    status: Optional[MenuItemStatus] = None


class MenuItemResponse(MenuItemBase):
    id: str
    cafe_id: str
    created_at: datetime
    updated_at: datetime


class MenuCategoryBase(BaseModel):
    name: str
    sort_order: int = 0
    is_active: bool = True


class MenuCategoryCreate(MenuCategoryBase):
    pass


class MenuCategoryResponse(MenuCategoryBase):
    id: str
    cafe_id: str


class DealCondition(BaseModel):
    min_cart_total_paise: int = 0
    required_item_ids: List[str] = Field(default_factory=list)


class DealDiscountType(str, Enum):
    PERCENTAGE = "percentage"
    FLAT_PAISE = "flat_paise"


class DealBase(BaseModel):
    title: str
    description: str = ""
    code: str
    discount_type: DealDiscountType = DealDiscountType.PERCENTAGE
    discount_value: int  # percentage (e.g. 10 for 10%) or flat paise (e.g. 5000 for Rs 50)
    max_discount_paise: Optional[int] = None
    condition: DealCondition = Field(default_factory=DealCondition)
    is_active: bool = True
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None


class DealCreate(DealBase):
    pass


class DealResponse(DealBase):
    id: str
    cafe_id: str
