import asyncio
import os
import sys
from typing import AsyncGenerator
import pytest

# Ensure app is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.modules.auth_tenancy.security import (
    create_access_token,
    create_customer_session_token,
    create_qr_token,
)
from app.modules.auth_tenancy.models import UserRole


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def cafe_a_id():
    return "cafe_aaa_1111111111111111"


@pytest.fixture
def cafe_b_id():
    return "cafe_bbb_2222222222222222"


@pytest.fixture
def cafe_a_staff_token(cafe_a_id):
    return create_access_token({
        "sub": "user_staff_a_1",
        "email": "staff@cafea.com",
        "name": "Staff A",
        "role": UserRole.STAFF.value,
        "cafe_id": cafe_a_id,
    })


@pytest.fixture
def cafe_b_staff_token(cafe_b_id):
    return create_access_token({
        "sub": "user_staff_b_1",
        "email": "staff@cafeb.com",
        "name": "Staff B",
        "role": UserRole.STAFF.value,
        "cafe_id": cafe_b_id,
    })


@pytest.fixture
def cafe_a_customer_session(cafe_a_id):
    session_id = "sess_cust_a_123"
    token = create_customer_session_token(
        session_id=session_id,
        cafe_id=cafe_a_id,
        table_id="table_1",
        table_number="4",
    )
    return {"token": token, "session_id": session_id, "cafe_id": cafe_a_id, "table_number": "4"}


@pytest.fixture
def async_db():
    from mongomock_motor import AsyncMongoMockClient
    client = AsyncMongoMockClient()
    return client["test_cafe_ai_waiter"]

