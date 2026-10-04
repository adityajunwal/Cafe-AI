from typing import Any, Callable, Dict, List, Optional
from app.modules.cafes.repository import CafeRepository
from app.modules.cart.service import CartService
from app.modules.menu.repository import DealRepository, MenuRepository
from app.modules.orders.models import OrderStatus
from app.modules.orders.service import OrderService
from app.modules.realtime.event_bus import EventBus
from app.logging import logger

AI_WAITING_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_menu",
            "description": "Search the cafe menu by name, keyword, dietary tags (veg, vegan, non-veg, jain), or category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Dish or item name, or keyword"},
                    "dietary_tag": {"type": "string", "description": "e.g. veg, vegan, non-veg, jain"},
                    "category": {"type": "string", "description": "Specific menu category"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_item_details",
            "description": "Get detailed description, price, options, and availability for a specific menu item.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "The unique ID of the menu item"},
                },
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_allergens",
            "description": "Fetch verified allergen information for a menu item. MUST be called whenever customer asks about allergens or ingredients.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "The unique ID of the menu item"},
                },
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_deals",
            "description": "Check current valid deals and promotions available for this cafe.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_cart",
            "description": "View current items in the customer's cart, subtotal, discounts, and total.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_cart",
            "description": "Add a menu item to the cart with optional add-ons and instructions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "ID of item to add"},
                    "quantity": {"type": "integer", "default": 1, "description": "Quantity to add"},
                    "special_instructions": {"type": "string", "description": "Cooking or dietary instructions"},
                },
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_from_cart",
            "description": "Remove an item from the customer's cart.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string", "description": "ID of item to remove"},
                },
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "place_order",
            "description": "Submit and place the final order from the customer's current cart.",
            "parameters": {
                "type": "object",
                "properties": {
                    "special_instructions": {"type": "string", "description": "Overall order notes"},
                    "customer_name": {"type": "string", "description": "Optional customer name"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_staff",
            "description": "Call cafe staff/waiter to the table for physical assistance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Reason for calling staff"},
                },
            },
        },
    },
]


class AIWaiterToolExecutor:
    def __init__(
        self,
        cafe_id: str,
        session_id: str,
        table_id: str,
        table_number: str,
        menu_repo: MenuRepository,
        deal_repo: DealRepository,
        cart_service: CartService,
        order_service: OrderService,
        cafe_repo: CafeRepository,
        event_bus: EventBus,
    ):
        self.cafe_id = cafe_id
        self.session_id = session_id
        self.table_id = table_id
        self.table_number = table_number
        self.menu_repo = menu_repo
        self.deal_repo = deal_repo
        self.cart_service = cart_service
        self.order_service = order_service
        self.cafe_repo = cafe_repo
        self.event_bus = event_bus

    async def execute(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if tool_name == "search_menu":
                return await self._search_menu(args)
            elif tool_name == "get_item_details":
                return await self._get_item_details(args.get("item_id", ""))
            elif tool_name == "get_allergens":
                return await self._get_allergens(args.get("item_id", ""))
            elif tool_name == "get_active_deals":
                return await self._get_active_deals()
            elif tool_name == "view_cart":
                return await self._view_cart()
            elif tool_name == "add_to_cart":
                return await self._add_to_cart(args)
            elif tool_name == "remove_from_cart":
                return await self._remove_from_cart(args.get("item_id", ""))
            elif tool_name == "place_order":
                return await self._place_order(args)
            elif tool_name == "call_staff":
                return await self._call_staff(args.get("reason", "Customer requested assistance"))
            else:
                return {"error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            logger.error(f"Tool execution error for {tool_name}: {e}")
            return {"error": str(e)}

    async def _search_menu(self, args: Dict[str, Any]) -> Dict[str, Any]:
        query = args.get("query", "").lower().strip()
        dietary_tag = args.get("dietary_tag", "").lower().strip()
        category = args.get("category", "").strip()

        all_items = await self.menu_repo.get_published_menu(self.cafe_id)
        results = []
        for item in all_items:
            if not item.get("is_available", True):
                continue
            if query and query not in item.get("name", "").lower() and query not in item.get("description", "").lower():
                continue
            if dietary_tag and dietary_tag not in [t.lower() for t in item.get("dietary_tags", [])]:
                continue
            if category and category.lower() != item.get("category", "").lower():
                continue

            results.append({
                "item_id": str(item["_id"]),
                "name": item["name"],
                "price_rupees": f"{item['price_paise'] / 100:.2f}",
                "category": item["category"],
                "dietary_tags": item.get("dietary_tags", []),
                "description": item.get("description", "")[:120],
            })
        return {"items": results[:10]}

    async def _get_item_details(self, item_id: str) -> Dict[str, Any]:
        item = await self.menu_repo.get_item(self.cafe_id, item_id)
        if not item:
            return {"error": "Item not found"}
        return {
            "item_id": str(item["_id"]),
            "name": item["name"],
            "description": item.get("description", ""),
            "price_rupees": f"{item['price_paise'] / 100:.2f}",
            "is_available": item.get("is_available", True),
            "dietary_tags": item.get("dietary_tags", []),
            "add_ons": [
                {"id": a["id"], "name": a["name"], "price_rupees": f"{a['price_paise'] / 100:.2f}"}
                for a in item.get("add_ons", [])
            ],
        }

    async def _get_allergens(self, item_id: str) -> Dict[str, Any]:
        item = await self.menu_repo.get_item(self.cafe_id, item_id)
        if not item:
            return {"error": "Item not found"}

        allergen_info = item.get("allergens", {})
        is_verified = allergen_info.get("is_verified", False)
        contains = allergen_info.get("contains", [])

        # Hard guardrail: If not verified, state clearly that it is unknown and require staff check
        disclaimer = (
            "Allergen information is cafe-verified."
            if is_verified
            else "Allergen data has NOT been verified for this item. Please confirm with staff before ordering."
        )

        return {
            "item_name": item["name"],
            "is_verified": is_verified,
            "contains_allergens": contains if is_verified else "Unknown / Unverified",
            "notes": allergen_info.get("notes"),
            "backend_disclaimer": disclaimer,
        }

    async def _get_active_deals(self) -> Dict[str, Any]:
        deals = await self.deal_repo.get_active_deals(self.cafe_id)
        return {
            "deals": [
                {
                    "code": d["code"],
                    "title": d["title"],
                    "description": d.get("description", ""),
                    "discount": f"{d['discount_value']}%" if d["discount_type"] == "percentage" else f"₹{d['discount_value']/100:.2f} off",
                }
                for d in deals
            ]
        }

    async def _view_cart(self) -> Dict[str, Any]:
        cart = await self.cart_service.get_or_create_cart(self.cafe_id, self.session_id, self.table_id)
        return {
            "items": [
                {
                    "item_id": i.item_id,
                    "name": i.name,
                    "quantity": i.quantity,
                    "price_rupees": f"{i.line_total_paise / 100:.2f}",
                }
                for i in cart.items
            ],
            "subtotal_rupees": f"{cart.subtotal_paise / 100:.2f}",
            "discount_rupees": f"{cart.discount_paise / 100:.2f}",
            "tax_rupees": f"{cart.tax_paise / 100:.2f}",
            "total_rupees": f"{cart.total_paise / 100:.2f}",
        }

    async def _add_to_cart(self, args: Dict[str, Any]) -> Dict[str, Any]:
        item_id = args.get("item_id")
        quantity = args.get("quantity", 1)
        instructions = args.get("special_instructions")
        cart = await self.cart_service.add_item_to_cart(
            cafe_id=self.cafe_id,
            session_id=self.session_id,
            table_id=self.table_id,
            item_id=item_id,
            quantity=quantity,
            special_instructions=instructions,
        )
        return {
            "status": "success",
            "message": f"Added to cart. Current cart total: ₹{cart.total_paise / 100:.2f}",
            "cart": cart.model_dump(),
        }

    async def _remove_from_cart(self, item_id: str) -> Dict[str, Any]:
        cart = await self.cart_service.remove_item_from_cart(
            cafe_id=self.cafe_id,
            session_id=self.session_id,
            table_id=self.table_id,
            item_id=item_id,
        )
        return {
            "status": "success",
            "message": f"Item removed. Current cart total: ₹{cart.total_paise / 100:.2f}",
            "cart": cart.model_dump(),
        }

    async def _place_order(self, args: Dict[str, Any]) -> Dict[str, Any]:
        order = await self.order_service.create_order_from_cart(
            cafe_id=self.cafe_id,
            session_id=self.session_id,
            table_id=self.table_id,
            table_number=self.table_number,
            special_instructions=args.get("special_instructions"),
            customer_name=args.get("customer_name"),
        )
        # Publish event
        await self.event_bus.publish(
            cafe_id=self.cafe_id,
            event_type="order.created",
            data={
                "order_id": str(order["_id"]),
                "table_number": self.table_number,
                "total_paise": order["total_paise"],
                "order_status": order["order_status"],
                "session_id": self.session_id,
            },
        )
        cafe = await self.cafe_repo.get_by_id(self.cafe_id)
        upi_id = cafe.get("upi_id", "cafe@upi") if cafe else "cafe@upi"
        return {
            "status": "success",
            "order_id": str(order["_id"]),
            "order_status": order["order_status"],
            "total_rupees": f"{order['total_paise'] / 100:.2f}",
            "payment_mode": order.get("order_status"),
            "upi_id": upi_id,
        }

    async def _call_staff(self, reason: str) -> Dict[str, Any]:
        await self.event_bus.publish(
            cafe_id=self.cafe_id,
            event_type="staff.called",
            data={
                "table_number": self.table_number,
                "table_id": self.table_id,
                "session_id": self.session_id,
                "reason": reason,
            },
        )
        return {"status": "success", "message": "Staff has been notified and is on the way to your table."}
