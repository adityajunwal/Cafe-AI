from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import uuid
from jose import JWTError, jwt
import bcrypt
from app.config import settings


def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception:
        return False


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError as e:
        raise ValueError(f"Invalid or expired token: {e}")


def create_qr_token(cafe_id: str, table_id: str, table_number: str) -> str:
    """Creates a verifiable signed token encoded into the table's physical QR code."""
    data = {
        "type": "table_qr",
        "cafe_id": cafe_id,
        "table_id": table_id,
        "table_number": table_number,
        "nonce": str(uuid.uuid4())[:8],
    }
    return jwt.encode(data, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_qr_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "table_qr":
            raise ValueError("Token is not a table QR token")
        return payload
    except JWTError as e:
        raise ValueError(f"Invalid QR token: {e}")


def create_customer_session_token(
    session_id: str,
    cafe_id: str,
    table_id: str,
    table_number: str,
) -> str:
    """Creates a short-lived signed session token for a customer who scanned a table QR."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.CUSTOMER_SESSION_EXPIRE_MINUTES)
    data = {
        "type": "customer_session",
        "session_id": session_id,
        "cafe_id": cafe_id,
        "table_id": table_id,
        "table_number": table_number,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(data, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_customer_session_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "customer_session":
            raise ValueError("Token is not a customer session token")
        return payload
    except JWTError as e:
        raise ValueError(f"Invalid customer session: {e}")


def create_ws_ticket(
    cafe_id: str,
    role: str,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> str:
    """Single-use signed WebSocket ticket with short expiry (e.g. 60 seconds)."""
    expire = datetime.now(timezone.utc) + timedelta(seconds=settings.WS_TICKET_EXPIRE_SECONDS)
    data = {
        "type": "ws_ticket",
        "jti": str(uuid.uuid4()),
        "cafe_id": cafe_id,
        "role": role,
        "session_id": session_id,
        "user_id": user_id,
        "exp": expire,
    }
    return jwt.encode(data, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_ws_ticket(ticket: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(ticket, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "ws_ticket":
            raise ValueError("Token is not a WebSocket ticket")
        return payload
    except JWTError as e:
        raise ValueError(f"Invalid or expired WebSocket ticket: {e}")
