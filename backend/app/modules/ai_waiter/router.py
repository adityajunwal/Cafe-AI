from typing import Any, Dict, List
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
from app.database import get_database
from app.modules.ai_waiter.llm_client import LLMClient
from app.modules.ai_waiter.service import AIWaiterService
from app.modules.auth_tenancy.dependencies import get_customer_session
from app.modules.auth_tenancy.models import CustomerSessionInfo
from app.modules.cafes.repository import CafeRepository
from app.modules.cart.repository import CartRepository
from app.modules.cart.service import CartService
from app.modules.menu.repository import DealRepository, MenuRepository
from app.modules.orders.repository import OrderRepository
from app.modules.orders.service import OrderService
from app.modules.realtime.event_bus import EventBus

router = APIRouter(prefix="/v1", tags=["AI Waiter Chatbot"])


class ChatTurnRequest(BaseModel):
    messages: List[Dict[str, Any]] = Field(description="History of chat messages with role and content")


def get_ai_waiter_service(db=Depends(get_database)) -> AIWaiterService:
    cafe_repo = CafeRepository(db)
    menu_repo = MenuRepository(db)
    deal_repo = DealRepository(db)
    cart_repo = CartRepository(db)
    order_repo = OrderRepository(db)
    event_bus = EventBus(db)

    cart_service = CartService(
        cart_repo=cart_repo,
        menu_repo=menu_repo,
        deal_repo=deal_repo,
        cafe_repo=cafe_repo,
    )
    order_service = OrderService(
        order_repo=order_repo,
        cart_repo=cart_repo,
        menu_repo=menu_repo,
        cafe_repo=cafe_repo,
    )
    llm_client = LLMClient()

    return AIWaiterService(
        cafe_repo=cafe_repo,
        menu_repo=menu_repo,
        deal_repo=deal_repo,
        cart_service=cart_service,
        order_service=order_service,
        event_bus=event_bus,
        llm_client=llm_client,
    )


@router.post("/chat")
async def chat_turn(
    data: ChatTurnRequest,
    request: Request,
    session: CustomerSessionInfo = Depends(get_customer_session),
    service: AIWaiterService = Depends(get_ai_waiter_service),
):
    """
    Streamed SSE response for customer AI waiter conversation.
    """
    stream = service.stream_chat_turn(
        cafe_id=session.cafe_id,
        session_id=session.session_id,
        table_id=session.table_id,
        table_number=session.table_number,
        messages=data.messages,
    )

    return EventSourceResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
