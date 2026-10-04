from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class OrderStatus(str, Enum):
    AWAITING_PAYMENT = "awaiting_payment"
    NEW = "new"
    PREPARING = "preparing"
    READY = "ready"
    SERVED = "served"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class PaymentStatus(str, Enum):
    UNPAID = "unpaid"
    SUBMITTED = "submitted"
    VERIFIED = "verified"
    REJECTED = "rejected"
    BILL_REQUESTED = "bill_requested"
    PAID = "paid"


class PaymentMethod(str, Enum):
    MANUAL_UPI = "manual_upi"
    CASH = "cash"
    CARD = "card"


class PaymentAttempt(BaseModel):
    attempt_id: str
    method: PaymentMethod = PaymentMethod.MANUAL_UPI
    amount_paise: int
    utr: Optional[str] = None
    screenshot_url: Optional[str] = None
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None


class OrderItemSnapshot(BaseModel):
    item_id: str
    name: str
    quantity: int = Field(ge=1)
    unit_price_paise: int = Field(ge=0)
    selected_add_ons: List[Dict[str, Any]] = Field(default_factory=list)
    special_instructions: Optional[str] = None
    line_total_paise: int = Field(ge=0)


class StatusHistoryEntry(BaseModel):
    status: str  # order_status or payment_status transition
    actor_type: str  # customer, staff, system, sweeper
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: Optional[str] = None


class OrderBase(BaseModel):
    cafe_id: str
    table_id: str
    table_number: str
    session_id: str
    order_status: OrderStatus
    payment_status: PaymentStatus
    items: List[OrderItemSnapshot]
    subtotal_paise: int
    discount_paise: int = 0
    tax_paise: int = 0
    service_charge_paise: int = 0
    total_paise: int
    special_instructions: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    staff_called: bool = False
    idempotency_key: Optional[str] = None


class OrderCreate(BaseModel):
    idempotency_key: Optional[str] = None
    special_instructions: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None


class OrderResponse(OrderBase):
    id: str
    payments: List[PaymentAttempt] = Field(default_factory=list)
    status_history: List[StatusHistoryEntry] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class PaymentSubmissionRequest(BaseModel):
    utr: Optional[str] = Field(default=None, description="UPI Transaction Reference (last 6-12 digits)")
    screenshot_url: Optional[str] = None


class PaymentVerificationRequest(BaseModel):
    action: str = Field(description="'approve' or 'reject'")
    rejection_reason: Optional[str] = None


class OrderTransitionRequest(BaseModel):
    to_status: OrderStatus
    notes: Optional[str] = None
