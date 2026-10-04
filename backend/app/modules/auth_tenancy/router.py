from datetime import datetime, timezone
from typing import Any, Dict
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.database import get_database
from app.modules.auth_tenancy.dependencies import get_current_user, get_customer_session, require_roles
from app.modules.auth_tenancy.models import (
    CustomerSessionInfo,
    CustomerSessionResponse,
    StaffUserCreate,
    StaffUserResponse,
    TokenResponse,
    UserRole,
)
from app.modules.auth_tenancy.security import (
    create_access_token,
    create_customer_session_token,
    create_ws_ticket,
    hash_password,
    verify_password,
    verify_qr_token,
)
from app.modules.cafes.repository import CafeRepository, TableRepository

router = APIRouter(prefix="/v1", tags=["Authentication & Tenancy"])


class LoginRequest(BaseModel):
    email: str
    password: str


class SessionCreateRequest(BaseModel):
    qr_token: str


class WSTicketResponse(BaseModel):
    ticket: str
    expires_in_seconds: int = 60


@router.post("/auth/login", response_model=TokenResponse)
async def login(data: LoginRequest, db=Depends(get_database)):
    user = await db.staff_users.find_one({"email": data.email.lower().strip()})
    if not user or not verify_password(data.password, user.get("hashed_password", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    token = create_access_token({
        "sub": str(user["_id"]),
        "email": user["email"],
        "name": user.get("name", ""),
        "role": user["role"],
        "cafe_id": user["cafe_id"],
    })

    return TokenResponse(
        access_token=token,
        role=UserRole(user["role"]),
        cafe_id=user["cafe_id"],
        name=user.get("name", ""),
    )


@router.post("/auth/staff", response_model=StaffUserResponse)
async def create_staff(
    data: StaffUserCreate,
    current_user: StaffUserResponse = Depends(require_roles(UserRole.OWNER, UserRole.PLATFORM_ADMIN)),
    db=Depends(get_database),
):
    # Enforce that owner can only create staff for their own cafe
    if current_user.role == UserRole.OWNER and data.cafe_id != current_user.cafe_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owners cannot create staff for another cafe",
        )

    existing = await db.staff_users.find_one({"email": data.email.lower().strip()})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists",
        )

    doc = {
        "email": data.email.lower().strip(),
        "hashed_password": hash_password(data.password),
        "name": data.name,
        "role": data.role.value,
        "cafe_id": data.cafe_id,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.staff_users.insert_one(doc)
    return StaffUserResponse(
        id=str(result.inserted_id),
        email=doc["email"],
        name=doc["name"],
        role=data.role,
        cafe_id=doc["cafe_id"],
        is_active=True,
    )


@router.post("/sessions", response_model=CustomerSessionResponse)
async def create_customer_session(data: SessionCreateRequest, db=Depends(get_database)):
    """Customer table entry: validates QR token and issues signed session token."""
    try:
        qr_payload = verify_qr_token(data.qr_token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    cafe_id = qr_payload["cafe_id"]
    table_id = qr_payload["table_id"]
    table_number = qr_payload["table_number"]

    # Verify table and cafe exist
    cafe_repo = CafeRepository(db)
    cafe = await cafe_repo.get_by_id(cafe_id)
    if not cafe:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cafe not found")

    session_id = str(uuid.uuid4())
    session_token = create_customer_session_token(
        session_id=session_id,
        cafe_id=cafe_id,
        table_id=table_id,
        table_number=table_number,
    )

    return CustomerSessionResponse(
        session_token=session_token,
        session_id=session_id,
        cafe_id=cafe_id,
        table_id=table_id,
        table_number=table_number,
        cafe_name=cafe.get("name"),
    )


@router.post("/ws-ticket", response_model=WSTicketResponse)
async def issue_staff_ws_ticket(
    current_user: StaffUserResponse = Depends(get_current_user),
):
    """Issues single-use WebSocket ticket for staff connection."""
    ticket = create_ws_ticket(
        cafe_id=current_user.cafe_id,
        role=current_user.role.value,
        user_id=current_user.id,
    )
    return WSTicketResponse(ticket=ticket)


@router.post("/customer/ws-ticket", response_model=WSTicketResponse)
async def issue_customer_ws_ticket(
    customer: CustomerSessionInfo = Depends(get_customer_session),
):
    """Issues single-use WebSocket ticket for customer session."""
    ticket = create_ws_ticket(
        cafe_id=customer.cafe_id,
        role="customer",
        session_id=customer.session_id,
    )
    return WSTicketResponse(ticket=ticket)

