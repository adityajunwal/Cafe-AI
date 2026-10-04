from typing import Any, Dict, List, Optional
from bson import ObjectId
from app.modules.cart.models import Cart, CartItem, SelectedAddOn
from app.modules.cart.repository import CartRepository
from app.modules.menu.repository import DealRepository, MenuRepository
from app.modules.cafes.repository import CafeRepository


class CartService:
    def __init__(
        self,
        cart_repo: CartRepository,
        menu_repo: MenuRepository,
        deal_repo: DealRepository,
        cafe_repo: CafeRepository,
    ):
        self.cart_repo = cart_repo
        self.menu_repo = menu_repo
        self.deal_repo = deal_repo
        self.cafe_repo = cafe_repo

    async def get_or_create_cart(self, cafe_id: str, session_id: str, table_id: str) -> Cart:
        data = await self.cart_repo.get_cart(cafe_id, session_id)
        if data:
            return Cart(**data)
        new_cart = Cart(session_id=session_id, cafe_id=cafe_id, table_id=table_id)
        await self.cart_repo.save_cart(cafe_id, session_id, new_cart.model_dump())
        return new_cart

    async def add_item_to_cart(
        self,
        cafe_id: str,
        session_id: str,
        table_id: str,
        item_id: str,
        quantity: int = 1,
        selected_add_on_ids: Optional[List[str]] = None,
        special_instructions: Optional[str] = None,
    ) -> Cart:
        # Mandatory rule: Always re-verify price and availability against MongoDB authoritative truth!
        menu_item = await self.menu_repo.get_item(cafe_id, item_id)
        if not menu_item:
            raise ValueError(f"Menu item '{item_id}' not found")
        if not menu_item.get("is_available", True):
            raise ValueError(f"'{menu_item['name']}' is currently sold out")

        # Resolve add-ons
        selected_add_ons: List[SelectedAddOn] = []
        add_ons_cost = 0
        if selected_add_on_ids:
            avail_add_ons = {a["id"]: a for a in menu_item.get("add_ons", [])}
            for aid in selected_add_on_ids:
                if aid in avail_add_ons:
                    add_on_obj = avail_add_ons[aid]
                    selected_add_ons.append(
                        SelectedAddOn(
                            id=aid,
                            name=add_on_obj["name"],
                            price_paise=add_on_obj["price_paise"],
                        )
                    )
                    add_ons_cost += add_on_obj["price_paise"]

        unit_price = menu_item["price_paise"] + add_ons_cost
        line_total = unit_price * quantity

        cart = await self.get_or_create_cart(cafe_id, session_id, table_id)

        # Check if identical item with same add-ons already exists
        existing_index = -1
        for idx, item in enumerate(cart.items):
            if (
                item.item_id == item_id
                and [a.id for a in item.selected_add_ons] == [a.id for a in selected_add_ons]
                and item.special_instructions == special_instructions
            ):
                existing_index = idx
                break

        if existing_index >= 0:
            cart.items[existing_index].quantity += quantity
            cart.items[existing_index].line_total_paise = (
                cart.items[existing_index].unit_price_paise * cart.items[existing_index].quantity
            )
        else:
            cart.items.append(
                CartItem(
                    item_id=item_id,
                    name=menu_item["name"],
                    quantity=quantity,
                    unit_price_paise=unit_price,
                    selected_add_ons=selected_add_ons,
                    special_instructions=special_instructions,
                    line_total_paise=line_total,
                )
            )

        await self._recalculate_and_save(cart)
        return cart

    async def update_cart_item(
        self,
        cafe_id: str,
        session_id: str,
        table_id: str,
        item_id: str,
        quantity: int,
        special_instructions: Optional[str] = None,
    ) -> Cart:
        cart = await self.get_or_create_cart(cafe_id, session_id, table_id)
        new_items: List[CartItem] = []
        for item in cart.items:
            if item.item_id == item_id:
                if quantity > 0:
                    item.quantity = quantity
                    item.line_total_paise = item.unit_price_paise * quantity
                    if special_instructions is not None:
                        item.special_instructions = special_instructions
                    new_items.append(item)
            else:
                new_items.append(item)

        cart.items = new_items
        await self._recalculate_and_save(cart)
        return cart

    async def remove_item_from_cart(
        self,
        cafe_id: str,
        session_id: str,
        table_id: str,
        item_id: str,
    ) -> Cart:
        return await self.update_cart_item(cafe_id, session_id, table_id, item_id, quantity=0)

    async def apply_deal(
        self,
        cafe_id: str,
        session_id: str,
        table_id: str,
        code: str,
    ) -> Cart:
        deal = await self.deal_repo.get_by_code(cafe_id, code)
        if not deal:
            raise ValueError(f"Invalid or expired promo code: {code}")

        cart = await self.get_or_create_cart(cafe_id, session_id, table_id)
        min_total = deal.get("condition", {}).get("min_cart_total_paise", 0)
        if cart.subtotal_paise < min_total:
            raise ValueError(f"Cart total must be at least ₹{min_total / 100:.2f} for this deal")

        cart.applied_deal_code = deal["code"]
        await self._recalculate_and_save(cart)
        return cart

    async def _recalculate_and_save(self, cart: Cart) -> None:
        subtotal = sum(i.line_total_paise for i in cart.items)
        cart.subtotal_paise = subtotal

        # Apply deal discount if exists
        discount = 0
        if cart.applied_deal_code:
            deal = await self.deal_repo.get_by_code(cart.cafe_id, cart.applied_deal_code)
            if deal and subtotal >= deal.get("condition", {}).get("min_cart_total_paise", 0):
                if deal["discount_type"] == "percentage":
                    discount = (subtotal * deal["discount_value"]) // 100
                else:
                    discount = deal["discount_value"]
                max_disc = deal.get("max_discount_paise")
                if max_disc:
                    discount = min(discount, max_disc)
            else:
                cart.applied_deal_code = None

        discount = min(discount, subtotal)
        cart.discount_paise = discount
        taxable_amount = subtotal - discount

        # Tax calculation
        cafe_doc = await self.cafe_repo.get_by_id(cart.cafe_id)
        tax_config = cafe_doc.get("tax_config", {}) if cafe_doc else {}
        tax_paise = 0
        if tax_config.get("gst_enabled", False):
            gst_rate = tax_config.get("gst_rate_percent", 5.0)
            tax_paise = int((taxable_amount * gst_rate) / 100)

        service_charge_paise = 0
        if tax_config.get("service_charge_percent", 0.0) > 0:
            sc_rate = tax_config.get("service_charge_percent", 0.0)
            service_charge_paise = int((taxable_amount * sc_rate) / 100)

        cart.tax_paise = tax_paise
        cart.service_charge_paise = service_charge_paise
        cart.total_paise = taxable_amount + tax_paise + service_charge_paise

        await self.cart_repo.save_cart(cart.cafe_id, cart.session_id, cart.model_dump())
