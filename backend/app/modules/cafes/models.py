from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class PaymentMode(str, Enum):
    PAY_NOW = "pay_now"
    PAY_AFTER = "pay_after"


class UpsellLevel(str, Enum):
    OFF = "off"
    LIGHT = "light"
    NORMAL = "normal"
    AGGRESSIVE = "aggressive"


class TaxConfig(BaseModel):
    gst_enabled: bool = False
    gst_rate_percent: float = 5.0  # Common for Indian restaurants/cafes
    service_charge_percent: float = 0.0
    is_composition_scheme: bool = False
    gstin: Optional[str] = None


class CafeBase(BaseModel):
    name: str
    slug: str
    upi_id: str = "cafe@upi"
    payment_mode: PaymentMode = PaymentMode.PAY_NOW
    upsell_level: UpsellLevel = UpsellLevel.NORMAL
    tax_config: TaxConfig = Field(default_factory=TaxConfig)
    auto_expire_unpaid_minutes: int = 15
    start_kitchen_before_payment: bool = False  # [Open] configurable setting
    currency: str = "INR"
    phone: Optional[str] = None
    address: Optional[str] = None


class CafeCreate(CafeBase):
    pass


class CafeUpdate(BaseModel):
    name: Optional[str] = None
    upi_id: Optional[str] = None
    payment_mode: Optional[PaymentMode] = None
    upsell_level: Optional[UpsellLevel] = None
    tax_config: Optional[TaxConfig] = None
    auto_expire_unpaid_minutes: Optional[int] = None
    start_kitchen_before_payment: Optional[bool] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class CafeResponse(CafeBase):
    id: str
    cache_version: int = 1
    created_at: datetime


class TableBase(BaseModel):
    number: str
    name: Optional[str] = None
    capacity: int = 4
    is_active: bool = True


class TableCreate(TableBase):
    pass


class TableResponse(TableBase):
    id: str
    cafe_id: str
    qr_token: str
    qr_url: Optional[str] = None
