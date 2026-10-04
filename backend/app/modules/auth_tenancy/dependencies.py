from typing import Optional
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.database import get_database
from app.modules.auth_tenancy.models import CustomerSessionInfo, StaffUserResponse, UserRole
from app.modules.auth_tenancy.security import decode_access_token, decode_customer_session_token
from app.logging import cafe_id_ctx, session_id_ctx

security_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
) -> StaffUserResponse:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(credentials.credentials)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )

    cafe_id = payload.get("cafe_id")
    role = payload.get("role")
    user_id = payload.get("sub")
    email = payload.get("email")
    name = payload.get("name", "")

    if not cafe_id or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload is missing essential claims",
        )

    # Set contextvar for logging
    cafe_id_ctx.set(cafe_id)

    return StaffUserResponse(
        id=user_id,
        email=email,
        name=name,
        role=UserRole(role),
        cafe_id=cafe_id,
        is_active=True,
    )


def require_roles(*allowed_roles: UserRole):
    def role_checker(user: StaffUserResponse = Depends(get_current_user)) -> StaffUserResponse:
        if user.role not in allowed_roles and user.role != UserRole.PLATFORM_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Action requires one of roles: {[r.value for r in allowed_roles]}",
            )
        return user
    return role_checker


async def get_customer_session(
    x_customer_session: Optional[str] = Header(None, alias="X-Customer-Session"),
) -> CustomerSessionInfo:
    """Authenticates a customer request using the signed customer session token."""
    if not x_customer_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Customer-Session header is required for customer ordering operations",
        )
    try:
        payload = decode_customer_session_token(x_customer_session)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )

    cafe_id = payload.get("cafe_id")
    session_id = payload.get("session_id")

    # Set contextvars for logging
    cafe_id_ctx.set(cafe_id)
    session_id_ctx.set(session_id)

    return CustomerSessionInfo(
        session_id=session_id,
        cafe_id=cafe_id,
        table_id=payload.get("table_id"),
        table_number=payload.get("table_number"),
    )
