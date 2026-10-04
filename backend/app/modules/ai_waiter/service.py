import asyncio
import json
from typing import Any, AsyncGenerator, Dict, List
import uuid
from app.modules.ai_waiter.llm_client import LLMClient
from app.modules.ai_waiter.tools import AI_WAITING_TOOLS, AIWaiterToolExecutor
from app.modules.cafes.repository import CafeRepository
from app.modules.cart.service import CartService
from app.modules.menu.repository import DealRepository, MenuRepository
from app.modules.orders.service import OrderService
from app.modules.realtime.event_bus import EventBus
from app.logging import logger


class AIWaiterService:
    def __init__(
        self,
        cafe_repo: CafeRepository,
        menu_repo: MenuRepository,
        deal_repo: DealRepository,
        cart_service: CartService,
        order_service: OrderService,
        event_bus: EventBus,
        llm_client: LLMClient,
    ):
        self.cafe_repo = cafe_repo
        self.menu_repo = menu_repo
        self.deal_repo = deal_repo
        self.cart_service = cart_service
        self.order_service = order_service
        self.event_bus = event_bus
        self.llm_client = llm_client

    async def _build_system_prompt(self, cafe_id: str, table_number: str) -> str:
        cafe = await self.cafe_repo.get_by_id(cafe_id)
        cafe_name = cafe.get("name", "Local Cafe") if cafe else "Local Cafe"
        payment_mode = cafe.get("payment_mode", "pay_now") if cafe else "pay_now"
        upi_id = cafe.get("upi_id", "cafe@upi") if cafe else "cafe@upi"

        return f"""You are the friendly, helpful AI Waiter for {cafe_name} at Table {table_number}.
Your primary role is to help customers discover delicious food, answer questions about dishes, allergens, and specials, build their cart, and place orders smoothly.

RULES YOU MUST ALWAYS FOLLOW:
1. SOURCE OF TRUTH:
   - You NEVER invent or guess menu items, prices, deals, taxes, or availability.
   - Always call the provided tools (`search_menu`, `get_item_details`, `get_allergens`, `get_active_deals`, `add_to_cart`, `view_cart`, `place_order`, etc.) to read and mutate data.

2. ALLERGEN SAFETY:
   - When asked about allergens or ingredients, YOU MUST call `get_allergens(item_id)`.
   - Never say an item is "safe" or allergen-free unless the tool explicitly reports verified data.
   - If allergen data is unverified or missing, you must state that it is unknown and recommend the customer confirm with the cafe staff. Always relay the backend disclaimer.

3. ORDERING & CART:
   - When the customer wants to order or add an item, call `add_to_cart`.
   - When the customer confirms they are ready to order, summarize the items and call `place_order`.
   - Current cafe payment mode: {payment_mode} (UPI ID: {upi_id}).
   - In pay-now mode, inform the customer that their order will be sent to the kitchen as soon as payment is submitted and verified.

4. TONE & EXPERIENCE:
   - Welcoming, polite, concise, and helpful.
   - Support the customer in any language they speak, but keep dish names recognizable as listed on the menu.
   - Remind the customer that if they ever prefer standard visual browsing, they can tap 'View Manual Menu' at any time.
"""

    async def stream_chat_turn(
        self,
        cafe_id: str,
        session_id: str,
        table_id: str,
        table_number: str,
        messages: List[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        message_id = str(uuid.uuid4())
        yield {"event": "message.start", "data": json.dumps({"message_id": message_id})}

        tool_executor = AIWaiterToolExecutor(
            cafe_id=cafe_id,
            session_id=session_id,
            table_id=table_id,
            table_number=table_number,
            menu_repo=self.menu_repo,
            deal_repo=self.deal_repo,
            cart_service=self.cart_service,
            order_service=self.order_service,
            cafe_repo=self.cafe_repo,
            event_bus=self.event_bus,
        )

        system_prompt = await self._build_system_prompt(cafe_id, table_number)
        conversation = [{"role": "system", "content": system_prompt}] + messages

        max_turns = 5
        turn_count = 0

        while turn_count < max_turns:
            turn_count += 1
            has_tool_call = False
            pending_tool_calls: List[Dict[str, Any]] = []

            async for chunk in self.llm_client.chat_stream(conversation, tools=AI_WAITING_TOOLS):
                c_type = chunk.get("type")

                if c_type == "text_delta":
                    yield {
                        "event": "message.delta",
                        "data": json.dumps({"text": chunk["content"]}),
                    }

                elif c_type == "tool_call":
                    has_tool_call = True
                    pending_tool_calls.append(chunk)
                    yield {
                        "event": "tool.status",
                        "data": json.dumps({
                            "tool": chunk["name"],
                            "status": "executing",
                            "label": f"Processing {chunk['name'].replace('_', ' ')}...",
                        }),
                    }

                elif c_type == "error":
                    yield {
                        "event": "error",
                        "data": json.dumps({"error": chunk["error"]}),
                    }
                    return

            if not has_tool_call:
                break

            # Execute tool calls and feed results back to the model
            for tc in pending_tool_calls:
                t_name = tc["name"]
                t_args = tc["arguments"]
                t_id = tc["id"]

                result = await tool_executor.execute(t_name, t_args)

                # Emit specific UI cards when relevant
                if t_name in ("add_to_cart", "remove_from_cart", "view_cart") and "cart" in result:
                    yield {
                        "event": "ui.cart",
                        "data": json.dumps(result["cart"]),
                    }

                if t_name == "place_order" and result.get("status") == "success":
                    yield {
                        "event": "ui.order",
                        "data": json.dumps(result),
                    }
                    if result.get("order_status") == "awaiting_payment":
                        yield {
                            "event": "ui.payment_card",
                            "data": json.dumps({
                                "order_id": result["order_id"],
                                "upi_id": result.get("upi_id"),
                                "total_rupees": result["total_rupees"],
                            }),
                        }

                # Append tool result to conversation history, preserving Gemini thought_signature
                tool_call_obj: Dict[str, Any] = {
                    "id": t_id,
                    "type": "function",
                    "function": {"name": t_name, "arguments": json.dumps(t_args)},
                }
                if tc.get("extra_content"):
                    tool_call_obj["extra_content"] = tc["extra_content"]

                conversation.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [tool_call_obj],
                })
                conversation.append({
                    "role": "tool",
                    "tool_call_id": t_id,
                    "content": json.dumps(result),
                })

        yield {"event": "message.end", "data": json.dumps({"message_id": message_id, "status": "completed"})}
