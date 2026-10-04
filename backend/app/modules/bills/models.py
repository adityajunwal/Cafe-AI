from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class BillTaxBreakdown(BaseModel):
    taxable_amount_paise: int
    cgst_percent: float = 2.5
    cgst_paise: int = 0
    sgst_percent: float = 2.5
    sgst_paise: int = 0
    service_charge_percent: float = 0.0
    service_charge_paise: int = 0
    total_tax_paise: int = 0


class BillResponse(BaseModel):
    id: str
    cafe_id: str
    cafe_name: str
    bill_number: str
    order_id: str
    table_number: str
    items: List[Dict[str, Any]]
    subtotal_paise: int
    discount_paise: int
    tax_breakdown: BillTaxBreakdown
    total_paise: int
    gstin: Optional[str] = None
    created_at: datetime
