from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class CustomerContactCreate(BaseModel):
    name: Optional[str] = Field(default=None, description="Customer name")
    phone: str = Field(description="Customer phone number (e.g. 10-digit Indian mobile number)")
    marketing_consent: bool = Field(default=False, description="Separate explicit consent for receiving promotional offers")
    consent_wording_version: str = Field(default="v1.0", description="Version of the consent disclaimer text presented to the customer")


class CustomerContactResponse(BaseModel):
    id: str
    cafe_id: str
    name: Optional[str]
    phone: str
    marketing_consent: bool
    created_at: datetime
