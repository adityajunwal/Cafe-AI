from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class UserRole(str, Enum):
    OWNER = "owner"
    STAFF = "staff"
    PLATFORM_ADMIN = "platform_admin"


class StaffUserBase(BaseModel):
    email: EmailStr
    name: str
    role: UserRole = UserRole.STAFF
    cafe_id: str
    is_active: bool = True


class StaffUserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: UserRole = UserRole.STAFF
    cafe_id: str


class OwnerRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, description="Password (at least 6 characters)")
    name: str = Field(description="Owner full name")
    phone: Optional[str] = None
    cafe_name: str = Field(description="Name of the cafe")
    cafe_slug: Optional[str] = None
    upi_id: Optional[str] = Field(default="cafe@upi", description="Cafe UPI ID for manual payments")
    address: Optional[str] = None



class StaffUserResponse(BaseModel):
    id: str
    email: EmailStr
    name: str
    role: UserRole
    cafe_id: str
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    cafe_id: str
    name: str


class CustomerSessionInfo(BaseModel):
    session_id: str
    cafe_id: str
    table_id: str
    table_number: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None


class CustomerSessionResponse(BaseModel):
    session_token: str
    session_id: str
    cafe_id: str
    table_id: str
    table_number: str
    cafe_name: Optional[str] = None
